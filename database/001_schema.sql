create extension if not exists pgcrypto;

do $$ begin
 create type stock_transaction_type as enum(
 'OPENING_BALANCE','PURCHASE','USAGE','DAMAGE','EXPIRY_DISPOSAL',
 'VERIFICATION_ADJUSTMENT','REVERSAL');
exception when duplicate_object then null; end $$;

do $$ begin
 create type stock_transaction_status as enum('CONFIRMED','REVERSED');
exception when duplicate_object then null; end $$;

create table if not exists products(
 id uuid primary key default gen_random_uuid(),
 product_code text not null unique,
 product_name text not null,
 brand text,
 category text not null,
 formulation text,
 composition_text text,
 base_unit text not null,
 reorder_level numeric(14,3) not null default 0,
 minimum_stock numeric(14,3) not null default 0,
 active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

create table if not exists product_active_ingredients(
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references products(id) on delete cascade,
 active_ingredient text not null,
 concentration text,
 unique(product_id,active_ingredient)
);

create table if not exists stock_locations(
 id uuid primary key default gen_random_uuid(),
 location_code text not null unique,
 location_name text not null,
 active boolean not null default true
);

create table if not exists stock_batches(
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references products(id),
 location_id uuid not null references stock_locations(id),
 batch_number text not null,
 expiry_date date,
 created_at timestamptz not null default now(),
 unique(product_id,location_id,batch_number)
);

create table if not exists stock_transactions(
 id uuid primary key default gen_random_uuid(),
 transaction_no text not null unique,
 transaction_type stock_transaction_type not null,
 product_id uuid not null references products(id),
 location_id uuid not null references stock_locations(id),
 batch_id uuid references stock_batches(id),
 quantity_in numeric(14,3) not null default 0 check(quantity_in>=0),
 quantity_out numeric(14,3) not null default 0 check(quantity_out>=0),
 unit text not null,
 effective_at timestamptz not null default now(),
 notes text,
 idempotency_key text not null unique,
 external_task_id text,
 external_activity_id text,
 reversal_of uuid references stock_transactions(id),
 status stock_transaction_status not null default 'CONFIRMED',
 created_at timestamptz not null default now(),
 check((quantity_in>0 and quantity_out=0) or (quantity_out>0 and quantity_in=0))
);

create table if not exists stock_reservations(
 id uuid primary key default gen_random_uuid(),
 external_task_id text not null,
 product_id uuid not null references products(id),
 location_id uuid not null references stock_locations(id),
 quantity_reserved numeric(14,3) not null check(quantity_reserved>0),
 quantity_consumed numeric(14,3) not null default 0,
 quantity_released numeric(14,3) not null default 0,
 unit text not null,
 required_date date,
 status text not null default 'ACTIVE',
 idempotency_key text not null unique,
 created_at timestamptz not null default now(),
 check(quantity_consumed+quantity_released<=quantity_reserved)
);

create table if not exists reservation_events(
 id uuid primary key default gen_random_uuid(),
 reservation_id uuid not null references stock_reservations(id),
 event_type text not null,
 idempotency_key text not null unique,
 created_at timestamptz not null default now()
);

create or replace view current_batch_availability as
select b.id batch_id,b.product_id,b.location_id,b.batch_number,b.expiry_date,
 coalesce(sum(case when st.status='CONFIRMED' then st.quantity_in-st.quantity_out else 0 end),0)::numeric(14,3) quantity_available,
 case when b.expiry_date<current_date then 'EXPIRED'
      when b.expiry_date<=current_date+interval '90 days' then 'EXPIRING_SOON'
      else 'USABLE' end status
from stock_batches b
left join stock_transactions st on st.batch_id=b.id
group by b.id;

create or replace view current_inventory as
select p.product_code,p.product_name,p.brand,p.category,p.base_unit unit,
 sl.location_code,
 coalesce(sum(case when st.status='CONFIRMED' then st.quantity_in-st.quantity_out else 0 end),0)::numeric(14,3) physical_stock,
 coalesce((select sum(r.quantity_reserved-r.quantity_consumed-r.quantity_released)
   from stock_reservations r where r.product_id=p.id and r.location_id=sl.id and r.status='ACTIVE'),0)::numeric(14,3) reserved_stock,
 (coalesce(sum(case when st.status='CONFIRMED' then st.quantity_in-st.quantity_out else 0 end),0)
 -coalesce((select sum(r.quantity_reserved-r.quantity_consumed-r.quantity_released)
   from stock_reservations r where r.product_id=p.id and r.location_id=sl.id and r.status='ACTIVE'),0))::numeric(14,3) available_stock
from products p cross join stock_locations sl
left join stock_transactions st on st.product_id=p.id and st.location_id=sl.id
where p.active=true and sl.active=true
group by p.id,sl.id;
