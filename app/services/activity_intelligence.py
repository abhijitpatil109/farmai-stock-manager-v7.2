from __future__ import annotations
from datetime import date,timedelta
from decimal import Decimal
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation

ENGINE_VERSION="6.0.0"

def _d(x): return dict(x) if x else None

def build_intelligence_context(crop_cycle_id,as_of_date=None,history_days=45):
    as_of_date=as_of_date or date.today()
    with connection() as c:
        cycle=c.execute("""SELECT cc.*,f.name_en farm_name_en,f.name_mr farm_name_mr,
          p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr
          FROM public.crop_cycles cc JOIN public.farms f ON f.id=cc.farm_id
          JOIN public.plots p ON p.id=cc.plot_id WHERE cc.id=%s""",(crop_cycle_id,)).fetchone()
        if not cycle: raise ActivityRegisterNotFound("Crop Cycle not found. (पीक चक्र सापडले नाही.)")
        baseline=cycle["dap_baseline_date"] or cycle["planting_date"]
        dap=(as_of_date-baseline).days if baseline else None
        if dap is not None and dap<0: raise ActivityRegisterValidation("as_of_date is before DAP baseline.")
        start=as_of_date-timedelta(days=history_days)
        acts=[dict(x) for x in c.execute("""SELECT a.id activity_id,ae.id execution_id,ae.execution_date,
          ae.dap_at_execution,ae.status,at.code activity_type_code,at.name_en activity_type_name_en,
          at.name_mr activity_type_name_mr
          FROM public.activity_executions ae JOIN public.activities a ON a.id=ae.activity_id
          JOIN public.activity_types at ON at.id=a.activity_type_id
          WHERE a.crop_cycle_id=%s AND ae.execution_date BETWEEN %s AND %s
          AND NOT EXISTS(SELECT 1 FROM public.activity_execution_corrections cx WHERE cx.original_execution_id=ae.id)
          ORDER BY ae.execution_date DESC,ae.created_at DESC""",(crop_cycle_id,start,as_of_date)).fetchall()]
        for a in acts:
            a["purposes"]=[dict(x) for x in c.execute("""SELECT ap.code,ap.name_en,ap.name_mr
              FROM public.activity_purpose_links l JOIN public.activity_purposes ap ON ap.id=l.activity_purpose_id
              WHERE l.activity_id=%s ORDER BY ap.sort_order""",(a["activity_id"],)).fetchall()]
            a["products"]=[dict(x) for x in c.execute("""SELECT p.id product_id,p.product_code,p.product_name,
              p.category,p.formulation,p.composition_text,p.base_unit,i.actual_total_quantity,i.actual_total_unit_code,
              COALESCE((SELECT jsonb_agg(jsonb_build_object('active_ingredient',pai.active_ingredient,'concentration',pai.concentration))
                FROM public.product_active_ingredients pai WHERE pai.product_id=p.id),'[]'::jsonb) active_ingredients
              FROM public.activity_execution_inputs i JOIN public.products p ON p.id=i.product_id
              WHERE i.execution_id=%s ORDER BY i.created_at""",(a["execution_id"],)).fetchall()]
        observations=[dict(x) for x in c.execute("""SELECT ao.id,ao.observed_at,ao.dap_at_observation,ot.code observation_type_code,
          ot.name_en observation_type_name_en,ot.name_mr observation_type_name_mr,ao.severity,ao.numeric_value,
          ao.value_unit_code,ao.description_en,ao.description_mr,ao.verification_status
          FROM public.activity_observations ao JOIN public.observation_types ot ON ot.id=ao.observation_type_id
          WHERE ao.crop_cycle_id=%s AND ao.observed_at::date BETWEEN %s AND %s ORDER BY ao.observed_at DESC""",
          (crop_cycle_id,start,as_of_date)).fetchall()]
        inventory=[dict(x) for x in c.execute("""SELECT ci.product_code,ci.product_name,ci.unit,ci.location_code,
          ci.physical_stock,ci.reserved_stock,ci.available_stock FROM public.current_inventory ci
          WHERE ci.location_code='MAIN' AND ci.product_code IN
          (SELECT DISTINCT p.product_code FROM public.activity_execution_inputs i JOIN public.products p ON p.id=i.product_id
           JOIN public.activity_executions ae ON ae.id=i.execution_id JOIN public.activities a ON a.id=ae.activity_id
           WHERE a.crop_cycle_id=%s) ORDER BY ci.product_code""",(crop_cycle_id,)).fetchall()]
    return {"engine_version":ENGINE_VERSION,"as_of_date":as_of_date,"dap":dap,"history_window":{"from":start,"to":as_of_date},
      "crop_cycle":_d(cycle),"recent_activities":acts,"observations":observations,"relevant_stock":inventory}

def _recommendations(ctx):
    acts=ctx["recent_activities"]; obs=ctx["observations"]; rec=[]
    evidence=[{"type":"ACTIVITY","activity_id":str(x["activity_id"]),"execution_id":str(x["execution_id"]),
               "date":str(x["execution_date"]),"dap":x["dap_at_execution"]} for x in acts[:5]]
    if not acts:
        rec.append({"recommendation_type":"DATA_GAP","action_code":"INSPECT",
          "title_en":"Inspect crop before recommending an application","title_mr":"वापराची शिफारस करण्यापूर्वी पिकाची पाहणी करा",
          "reason_en":"No recent completed activity is available in the selected history window.",
          "reason_mr":"निवडलेल्या इतिहास कालावधीत अलीकडील पूर्ण क्रियाकलाप उपलब्ध नाही.",
          "confidence":"INSUFFICIENT_DATA","evidence":[],"warnings":["NO_RECENT_ACTIVITY"]})
    if not obs:
        rec.append({"recommendation_type":"OBSERVATION_GAP","action_code":"INSPECT",
          "title_en":"Record a current crop observation","title_mr":"सध्याचे पीक निरीक्षण नोंदवा",
          "reason_en":"Recent activity exists but no crop outcome/observation is available to verify response.",
          "reason_mr":"अलीकडील क्रियाकलाप उपलब्ध आहेत, परंतु प्रतिसाद पडताळण्यासाठी पीक परिणाम/निरीक्षण उपलब्ध नाही.",
          "confidence":"MEDIUM" if acts else "INSUFFICIENT_DATA","evidence":evidence,"warnings":["OUTCOME_NOT_RECORDED"]})
    # Conservative repetition signal: same product used in >=2 non-superseded executions in 14 days.
    cutoff=ctx["as_of_date"]-timedelta(days=14); uses={}
    for a in acts:
        if a["execution_date"]<cutoff: continue
        for p in a["products"]:
            uses.setdefault(p["product_code"],[]).append(a)
    for code,rows in uses.items():
        if len(rows)>=2:
            rec.append({"recommendation_type":"RECENT_REPETITION","action_code":"INSPECT",
              "title_en":f"Review recent repetition of {code}","title_mr":f"{code} च्या अलीकडील पुनर्वापराचे पुनरावलोकन करा",
              "reason_en":f"{code} appears in {len(rows)} executions within the last 14 days. Inspect need before repeating.",
              "reason_mr":f"गेल्या १४ दिवसांत {code} {len(rows)} अंमलबजावण्यांमध्ये वापरले आहे. पुन्हा वापरण्यापूर्वी गरज तपासा.",
              "confidence":"HIGH","evidence":[{"type":"ACTIVITY","activity_id":str(r["activity_id"]),"date":str(r["execution_date"])} for r in rows],
              "warnings":["RECENT_PRODUCT_REPETITION"]})
    if not rec:
        rec.append({"recommendation_type":"CURRENT_STATE","action_code":"INSPECT",
          "title_en":"Review current crop condition","title_mr":"सध्याच्या पिकाच्या स्थितीचे पुनरावलोकन करा",
          "reason_en":"History is available, but Phase 6.0 will not manufacture a chemical or nutrient prescription without an explicit agronomic rule/evidence.",
          "reason_mr":"इतिहास उपलब्ध आहे; परंतु स्पष्ट कृषी नियम/पुरावा नसताना Phase 6.0 रासायनिक किंवा अन्नद्रव्य शिफारस तयार करणार नाही.",
          "confidence":"MEDIUM","evidence":evidence,"warnings":[]})
    return rec

def evaluate_intelligence(crop_cycle_id,as_of_date=None,history_days=45,persist=False):
    ctx=build_intelligence_context(crop_cycle_id,as_of_date,history_days); recs=_recommendations(ctx)
    if persist:
      with connection() as c:
        try:
          for r in recs:
            row=c.execute("""INSERT INTO public.intelligence_recommendations(
              crop_cycle_id,as_of_date,dap,recommendation_type,action_code,title_en,title_mr,reason_en,reason_mr,
              confidence,evidence,warnings,engine_version) VALUES
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id""",
              (crop_cycle_id,ctx["as_of_date"],ctx["dap"],r["recommendation_type"],r["action_code"],r["title_en"],r["title_mr"],
               r["reason_en"],r["reason_mr"],r["confidence"],__import__("json").dumps(r["evidence"]),
               __import__("json").dumps(r["warnings"]),ENGINE_VERSION)).fetchone()
            r["recommendation_id"]=str(row["id"])
          c.commit()
        except Exception:c.rollback();raise
    return {"context":ctx,"analysis":intelligence_analysis(ctx),"recommendations":recs}

def decide_recommendation(recommendation_id,req):
    with connection() as c:
      try:
        row=c.execute("SELECT * FROM public.intelligence_recommendations WHERE id=%s FOR UPDATE",(recommendation_id,)).fetchone()
        if not row: raise ActivityRegisterNotFound("Recommendation not found. (शिफारस सापडली नाही.)")
        if row["status"]!="PROPOSED": raise ActivityRegisterValidation("Recommendation is no longer PROPOSED.")
        c.execute("""INSERT INTO public.intelligence_feedback(recommendation_id,decision,reason_en,reason_mr,decided_by)
          VALUES(%s,%s,%s,%s,%s)""",(recommendation_id,req.decision,req.reason_en,req.reason_mr,req.decided_by))
        c.execute("UPDATE public.intelligence_recommendations SET status=%s WHERE id=%s",(req.decision,recommendation_id))
        c.commit();return {"recommendation_id":str(recommendation_id),"status":req.decision}
      except Exception:c.rollback();raise


def nutrient_summary(ctx):
    totals={}
    with connection() as c:
      for a in ctx["recent_activities"]:
        for p in a["products"]:
          qty=p.get("actual_total_quantity")
          unit=(p.get("actual_total_unit_code") or "").upper()
          if qty is None or unit not in ("KG","G"): continue
          kg=Decimal(str(qty)) if unit=="KG" else Decimal(str(qty))/Decimal("1000")
          profiles=c.execute("""SELECT nutrient_code,percentage,verification_status FROM public.product_nutrient_profiles
            WHERE product_id=%s AND verification_status='CONFIRMED'""",(p["product_id"],)).fetchall()
          for n in profiles:
            contribution=kg*Decimal(str(n["percentage"]))/Decimal("100")
            totals[n["nutrient_code"]]=totals.get(n["nutrient_code"],Decimal("0"))+contribution
    return [{"nutrient_code":k,"confirmed_contribution_kg":float(v)} for k,v in sorted(totals.items())]

def rotation_signals(ctx):
    cutoff=ctx["as_of_date"]-timedelta(days=30); uses={}
    with connection() as c:
      for a in ctx["recent_activities"]:
        if a["execution_date"]<cutoff: continue
        for p in a["products"]:
          rows=c.execute("""SELECT classification_system,group_code,active_ingredient,verification_status
            FROM public.product_rotation_metadata WHERE product_id=%s AND verification_status='CONFIRMED'""",(p["product_id"],)).fetchall()
          for r in rows:
            key=(r["classification_system"],r["group_code"])
            uses.setdefault(key,[]).append({"date":str(a["execution_date"]),"product_code":p["product_code"],
                                            "active_ingredient":r["active_ingredient"]})
    return [{"classification_system":k[0],"group_code":k[1],"uses":v,"repeat_count":len(v),
             "warning":len(v)>=2} for k,v in sorted(uses.items())]

def crop_stage(ctx):
    crop=(ctx["crop_cycle"]["crop_name_en"] or "").lower(); dap=ctx["dap"]
    with connection() as c:
      rows=c.execute("""SELECT rule_code,stage_name_en,stage_name_mr,dap_from,dap_to,rule_payload,priority
        FROM public.intelligence_rule_packs WHERE active=true AND lower(crop_name_en)=%s AND rule_type='STAGE'
        AND (%s IS NULL OR (COALESCE(dap_from,0)<=%s AND (dap_to IS NULL OR dap_to>=%s)))
        ORDER BY priority,version DESC""",(crop,dap,dap,dap)).fetchall()
    return [dict(x) for x in rows]

def intelligence_analysis(ctx):
    return {"nutrient_summary":nutrient_summary(ctx),"rotation_signals":rotation_signals(ctx),
            "crop_stage_matches":crop_stage(ctx),
            "guardrail":"Only CONFIRMED normalized nutrient/rotation metadata contributes to quantitative intelligence."}
