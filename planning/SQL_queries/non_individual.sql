Non-Individual Investors-

Default Query-

select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( true ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0

With OTM - Yes

select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1

inner join sphmf.customer_master cm

on cm.folio_no = dim1.folio_number

WHERE EXISTS(

SELECT

FROM SPHMF.MULTIPLE_BANK MB1

WHERE DIM1.FOLIO_NUMBER = MB1.FOLIO_NO

AND mb1.om_umrn is NOT null

AND (mb1.cease_dt is null OR CEASE_DT < CURRENT_DATE)

AND mb1.paymech in

(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true)) and dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( true ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0



With OTM - No
select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(sele

ct distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1

inner join sphmf.customer_master cm

on cm.folio_no = dim1.folio_number

WHERE NOT EXISTS(

-- Subquery gives list of folio's having otm

SELECT

FROM SPHMF.MULTIPLE_BANK MB1

WHERE DIM1.FOLIO_NUMBER = MB1.FOLIO_NO

AND mb1.om_umrn is NOT null

AND (mb1.cease_dt is null OR CEASE_DT < CURRENT_DATE)

AND mb1.paymech in

(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true)) and dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( true ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0

With Active Investor Type Filter-

select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( true ) and (i.uuid in ( select distinct map.id from (select max(date(pd.l_trxn_date)) as date,dim.investor_uuid id from sphmf.customer_schemes pd INNER JOIN distributor_investor_mapping dim on pd.folio_no=dim.folio_number where arn_code = ? group by dim.investor_uuid )map where CURRENT_DATE - date <=180 )) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0

With Dormant Investor Type Filter-

select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( true ) and (i.uuid in ( select distinct map.id from (select max(date(pd.l_trxn_date)) as date,dim.investor_uuid id from sphmf.customer_schemes pd INNER JOIN distributor_investor_mapping dim on pd.folio_no=dim.folio_number where arn_code = ? group by dim.investor_uuid )map where CURRENT_DATE - date >=180 )) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0

With CGF Investor Subtype-

Select count(*) from( select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number where ( ( i.uuid in(select distinct dim.investor_uuid id from sphmf.customer_schemes pd inner join distributor_investor_mapping dim on dim.folio_number=pd.folio_no where arn_code = ? and ( pd.sch_code in (select schcode from sphmf.scheme_setup where cgf_flag = 'C' and plan_type <> 'D') ) ) ) ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number ) count

With Minor and CGF  Investor Sub-Type-
Select count(*) from( select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number INNER JOIN sphmf.customer_master cm on cm.folio_no=dim.folio_number where ( ( i.uuid in(select distinct dim.investor_uuid id from sphmf.customer_schemes pd inner join distributor_investor_mapping dim on dim.folio_number=pd.folio_no where arn_code = ? and ( pd.sch_code in (select schcode from sphmf.scheme_setup where cgf_flag = 'C' and plan_type <> 'D') ) ) ) or ( cm.inv_type = '02' or cm.inv_type ='26' ) ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number ) count

With Minor Investor Subtype-
Select count(*) from( select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number INNER JOIN sphmf.customer_master cm on cm.folio_no=dim.folio_number where ( ( cm.inv_type = '02' or cm.inv_type ='26' ) ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number ) count

With Others Investor Subtype Filter-

select uuid,first_name,email,mobile_number,pan_number,dob,folio_number,bool_or(OTM) as otm from(select distinct on(pan_number) i.pan_number,trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')), ltrim(concat(nullif(i.middle_name, NULL), ' ')),ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.email, i.mobile_number, i.uuid, i.dob ,dim.folio_number,case when (ib.acno_valid!='R' AND ib.paymech IN(select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true) AND ib.om_umrn is NOT null AND (ib.cease_dt is null OR CEASE_DT < CURRENT_DATE)) then true else false end OTM from corporate_investor i inner join (select distinct investor_uuid ,folio_number from distributor_investor_mapping dim1 inner join sphmf.customer_master cm on cm.folio_no=dim1.folio_number where dim1.arn_code = ?) dim on i.uuid=dim.investor_uuid left join sphmf.multiple_bank ib on ib.folio_no=dim.folio_number INNER JOIN sphmf.customer_master cm on cm.folio_no=dim.folio_number where ( ( i.uuid in(select distinct dim.investor_uuid id from sphmf.customer_schemes pd inner join distributor_investor_mapping dim on dim.folio_number=pd.folio_no where arn_code = ? and ( pd.sch_code not in (select schcode from sphmf.scheme_setup where cgf_flag = 'C' and plan_type <> 'D') ) ) ) and ( not( cm.inv_type = '02' or cm.inv_type ='26') ) ) and (true) AND ( (case when ? <> '' then lower(i.first_name) ILIKE ? else true end) ) order by pan_number,created_time desc) investors group by uuid,first_name,email,mobile_number,pan_number,dob,folio_number order by first_name ASC limit 25 offset 0



