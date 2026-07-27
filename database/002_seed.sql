insert into stock_locations(location_code,location_name)
values('MAIN','Main Farm Store')
on conflict(location_code) do nothing;

insert into products(product_code,product_name,category,base_unit,reorder_level,minimum_stock)
values
('FERT-CN','Calcium Nitrate','Fertilizers','kg',10,5),
('FERT-AS','Ammonium Sulphate','Fertilizers','kg',10,5),
('FERT-191919','19:19:19','Fertilizers','kg',5,2),
('FERT-005234','00:52:34','Fertilizers','kg',5,2),
('FERT-126100','12:61:00','Fertilizers','kg',5,2),
('FERT-134013','13:40:13','Fertilizers','kg',5,2),
('FERT-113624','11:36:24','Fertilizers','kg',5,2),
('FERT-PS','Potassium Schoenite','Fertilizers','kg',5,2),
('FERT-MGSO4','Magnesium Sulphate','Fertilizers','kg',5,2),
('MICRO-METRO','Metro Plus','Micronutrients','g',500,200),
('MICRO-SUPER','Super Combi','Micronutrients','g',300,100),
('FUNG-BAV','Bavistin','Fungicides','g',500,200),
('FUNG-M45','M-45','Fungicides','g',500,200),
('INSECT-COR','Coragen','Insecticides','ml',150,50),
('INSECT-PROF','Profex','Insecticides','ml',250,100),
('INSECT-ACT','Actara','Insecticides','g',50,20),
('INSECT-EMI','Emida','Insecticides','ml',250,100)
on conflict(product_code) do nothing;
