--- This is the function call for when there is no filter selected in the UI
--- Individual Investors-
--- Default Query-

SELECT *
FROM filter_dp_investor_menu(
       'ARN-0411',
       'ALL',
       'ALL',
       'ALL',
       ARRAY[]::TEXT[],  -- empty text array
       ROW('ALL', ARRAY['ALL'], ARRAY['Z','N','Y']),
       ROW('ALL', ARRAY['SIP','STP','SWP','FLEXSTP','FLEXINDEX','DTP','SWINGSTP','SMARTSWAP','FLEXSIP'], ARRAY['ALL'], ARRAY['Z','N','Y']),
       ROW('ALL', ARRAY['PURCHASE','SWITCH','REDEMPTION','SIP','DTP','STP','SWP','FLEXSIP'], ARRAY['ALL'], ARRAY['Z','N','Y'], '1 month'),
       NULL,
       'first_name',
       'ASC',
       25,
       0,
       'Y'
    );


/*
Filter data is added in the above Query as selected by Broker. In case no filter for CurrentHolding , Systematic Filter and Investor Activity Filter is selected then same function is called in below manner-
*/
select * from filter_dp_investor_menu('ARN-0411','ALL','ALL','ALL',ARRAY[]::TEXT[],(null),
                                     (null),(null),null,'first_name','ASC','25',0,'Y');

—-- Individual call function 

-- DROP FUNCTION public.filter_dp_investor_menu(varchar, varchar, varchar, varchar, _text, current_holdings, systematic_plan, investor_activity, varchar, varchar, varchar, int4, int4, bpchar);
CREATE OR REPLACE FUNCTION public.filter_dp_investor_menu(arncode character varying, eligibility character varying, otm character varying, investortype character varying, investorsubtype text[], holding current_holdings, systematic systematic_plan, activity investor_activity, searchtext character varying, sortkey character varying, sortvalue character varying, pagelimit integer, pageindex integer, allowbroker character)
RETURNS TABLE(uuid character varying, name text, pan_number character varying, dob date, email character varying, mobile_number character varying, count integer, orderby character varying)
LANGUAGE plpgsql
AS $function$
DECLARE
   uuids uuid[];
   cgf_uuids uuid[];
   minor_uuids uuid[];
   others_uuids uuid[];
   otm_uuids uuid[];
   holding_uuids uuid[];
   sys_uuids uuid[];
   sip_uuids uuid[];
   dtp_uuids uuid[];
   flexindex_uuids uuid[];
   activity_uuids uuid[];
   systematic_plans text[] := ARRAY['SIP','STP','SWP','FLEXSTP','SWINGSTP','SMARTSWAP','FLEXSIP'];
   all_check varchar[] := ARRAY['ALL'];
   all_inv_check varchar[] := ARRAY['Z','Y','N'];
BEGIN
   uuids := ARRAY(select distinct dim.investor_uuid from distributor_investor_mapping dim inner join investor i on i.uuid = dim.investor_uuid  where dim.arn_code = arnCode);
   raise notice '1. uuids: %',cardinality(uuids);
   if eligibility = 'YES' and cardinality(uuids)>0 then
       uuids := ARRAY(select distinct dim.investor_uuid from distributor_investor_mapping dim inner join sphmf.customer_master cm on dim.folio_number = cm.folio_no where dim.arn_code=arnCode and dim.investor_uuid = ANY(uuids) and cm.email is not null);
   elsif eligibility = 'NO' and cardinality(uuids)>0 then
       uuids := ARRAY(select distinct dim.investor_uuid from distributor_investor_mapping dim LEFT JOIN sphmf.customer_master cm ON dim.folio_number = cm.folio_no WHERE dim.arn_code=arnCode and  dim.investor_uuid = ANY(uuids) GROUP BY dim.investor_uuid HAVING every(cm.email IS NULL));
   end if;
   raise notice '2. uuids: %',cardinality(uuids);
   if otm != 'ALL' and cardinality(uuids)>0 then
       otm_uuids := ARRAY(select distinct investor_uuid from distributor_investor_mapping dim
                                                                 inner join sphmf.customer_master cm on cm.folio_no=dim.folio_number
                          WHERE EXISTS  (SELECT FROM sphmf.multiple_bank mb
                                         WHERE dim.folio_number = mb.FOLIO_NO
                                           AND mb.om_umrn is NOT null
                                           AND (mb.cease_dt is null OR CEASE_DT < CURRENT_DATE)
                                           AND mb.paymech in (select distinct pay_mech from payout_mechanism where otm_flag is true and active_flag is true))
                            and dim.arn_code=arnCode and dim.investor_uuid=ANY(uuids));
       if otm = 'NOT_AVAILABLE' then
           uuids := array_subtract(uuids, otm_uuids);
       else
           uuids := otm_uuids;
       end if;
   end  if;
   raise notice '3. uuids: %',cardinality(uuids);
   if investorType = 'ACTIVE' and cardinality(uuids)>0 then
       uuids := ARRAY(select distinct map.id from
           (select max(date(pd.l_trxn_date)) as date,dim.investor_uuid id from sphmf.customer_schemes pd
                                                                                   INNER JOIN distributor_investor_mapping dim on pd.folio_no=dim.folio_number
            where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids) group by dim.investor_uuid )map where CURRENT_DATE - date <=180);
   elsif investorType = 'DORMANT' and cardinality(uuids)>0 then
       uuids := ARRAY(select distinct map.id from
           (select max(date(pd.l_trxn_date)) as date,dim.investor_uuid id from sphmf.customer_schemes pd
                                                                                   INNER JOIN distributor_investor_mapping dim on pd.folio_no=dim.folio_number
            where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids) group by dim.investor_uuid )map where CURRENT_DATE - date >=180);
   end if;
   raise notice '4. uuids: %',cardinality(uuids);
   if investorSubType @> ARRAY['CGF'] and cardinality(uuids)>0 then
       cgf_uuids := ARRAY(select  distinct dim.investor_uuid from sphmf.customer_schemes pd
                                                                      inner join distributor_investor_mapping dim on dim.folio_number=pd.folio_no
                          where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                            and ( pd.sch_code  in (select schcode from sphmf.scheme_setup where cgf_flag = 'C' and plan_type <> 'D')));
       raise notice '5. cgf_uuids: %',cardinality(cgf_uuids);
   end if;
   if investorSubType @> ARRAY['MINOR'] and cardinality(uuids)>0 then
       minor_uuids := ARRAY(select distinct dim.investor_uuid from distributor_investor_mapping dim
                                                                       inner join sphmf.customer_master cm on cm.folio_no=dim.folio_number
                                                                       inner join tax_status ts on cm.inv_type = ts.inv_type_code
                            where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids) and ts.distributor_flag='Y' and ts.minor_flag='Y' and ts.active_flag='Y'
           );
       raise notice '6. minor_uuids: %',cardinality(minor_uuids);
   end if;
   if investorSubType @> ARRAY['OTHERS'] and cardinality(uuids)>0 then
       others_uuids := ARRAY(select distinct dim.investor_uuid from distributor_investor_mapping dim
                                                                        INNER JOIN sphmf.customer_master cm on cm.folio_no=dim.folio_number
                                                                        inner join tax_status ts on cm.inv_type = ts.inv_type_code
                             where dim.investor_uuid in
                                   (select  distinct dim.investor_uuid from sphmf.customer_schemes pd
                                                                                inner join distributor_investor_mapping dim on dim.folio_number=pd.folio_no
                                    where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                                      and ( pd.sch_code not in (select schcode from sphmf.scheme_setup where cgf_flag = 'C' and plan_type <> 'D')))
                               and not(ts.distributor_flag='Y' and ts.minor_flag='Y' and ts.active_flag='Y'));
       raise notice '7. others_uuids: %',cardinality(others_uuids);
   end if;
   if investorSubType && ARRAY['CGF','OTHERS','MINOR'] then
       uuids := cgf_uuids || minor_uuids || others_uuids;
   end if;
   raise notice '8. uuids: %',cardinality(uuids);
   if cardinality(uuids) > 0 and (holding.is_holding != 'ALL') then
       holding_uuids := ARRAY(
               SELECT distinct investor_uuid
               FROM distributor_investor_mapping dim
                        INNER JOIN
                    (SELECT pt.folio_no, pt.broker_code, pt.sch_code FROM sphmf.processed_trxns pt
                                                                              INNER JOIN sphmf.customer_schemes cs ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code
                                                                              INNER JOIN scheme_master sm ON pt.sch_code = sm.scheme_cd AND sm.allow_broker = allowbroker
                     WHERE pt.broker_code=arnCode
                       AND CASE WHEN holding.schemes @> all_check THEN TRUE ELSE pt.sch_code=ANY(holding.schemes) END
                       AND CASE WHEN holding.inv_options @> all_check THEN TRUE ELSE cs.div_reinv_flag=ANY(holding.inv_options) END
                     GROUP BY pt.folio_no, pt.broker_code, pt.sch_code
                     HAVING (SUM(CASE WHEN trxn_sign = '-' THEN units * -1 WHEN trxn_sign = '+' THEN units ELSE 0 END)
                                ) > 0
                    ) holdings
                    ON dim.folio_number = holdings.folio_no and dim.arn_code = holdings.broker_code
               where dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
           );
       raise notice '9. holding_uuids: %',cardinality(holding_uuids);
       if holding.is_holding = 'false' then
           uuids := array_subtract(uuids, holding_uuids);
       else
           uuids := holding_uuids;
       end if;
   end if;
   raise notice '10. uuids: %',cardinality(uuids);
   if cardinality(uuids) > 0 and (systematic.is_active != 'ALL')  then
       if(systematic.plan && systematic_plans or systematic.plan @> all_check::text[]) then
           if(systematic.inv_options = all_inv_check) then
               sip_uuids := ARRAY(
                       SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                              INNER JOIN sphmf.SIPSTP s on dim.folio_number = s.folio_no and dim.arn_code = s.brok_code
                                                              INNER JOIN scheme_master sm ON s.sch_code = sm.scheme_cd AND sm.allow_broker = allowbroker
                       WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                         AND ((case when systematic.plan @> ARRAY['SIP'] then s.atrxn_type = 'P' end) or
                              (case when systematic.plan @> ARRAY['STP'] then (s.atrxn_type ='SO' AND (switch_flag IS NULL OR switch_flag NOT IN ('T','Q'))) end) or
                              (case when systematic.plan @> ARRAY['SWP'] then (s.atrxn_type ='R' AND (sub_trxn_type IS NULL OR sub_trxn_type !='MB')) end) or
                              (case when systematic.plan @> ARRAY['FLEXSTP'] then (s.atrxn_type ='SO') end) or
                              (case when systematic.plan @> ARRAY['SWINGSTP'] then (s.atrxn_type ='SO' AND switch_flag='Q') end) or
                              (case when systematic.plan @> ARRAY['SMARTSWAP'] then (s.atrxn_type='R' AND sub_trxn_type='MB') end) or
                              (case when systematic.plan @> ARRAY['FLEXSIP'] then (s.atrxn_type = 'P' AND s.sub_trxn_type='FS') end))
                         AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE s.sch_code=ANY(systematic.schemes) END
                         AND s.cease_dt IS NULL AND s.cancellation_request_date IS NULL AND s.to_date IS NOT NULL AND s.to_date > NOW());
           else
               sip_uuids := ARRAY(
                       SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                              INNER JOIN sphmf.SIPSTP s on dim.folio_number = s.folio_no and dim.arn_code = s.brok_code
                                                              INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = s.sch_code AND cs.folio_no=s.folio_no
                                                              INNER JOIN scheme_master sm ON s.sch_code = sm.scheme_cd AND sm.allow_broker = allowbroker
                       WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                         AND ((case when systematic.plan @> ARRAY['SIP'] then s.atrxn_type = 'P' end) or
                              (case when systematic.plan @> ARRAY['STP'] then (s.atrxn_type ='SO' AND (switch_flag IS NULL OR switch_flag NOT IN ('T','Q'))) end) or
                              (case when systematic.plan @> ARRAY['SWP'] then (s.atrxn_type ='R' AND (sub_trxn_type IS NULL OR sub_trxn_type !='MB')) end) or
                              (case when systematic.plan @> ARRAY['FLEXSTP'] then (s.atrxn_type ='SO') end) or
                              (case when systematic.plan @> ARRAY['SWINGSTP'] then (s.atrxn_type ='SO' AND switch_flag='Q') end) or
                              (case when systematic.plan @> ARRAY['SMARTSWAP'] then (s.atrxn_type='R' AND sub_trxn_type='MB') end) or
                              (case when systematic.plan @> ARRAY['FLEXSIP'] then (s.atrxn_type = 'P' AND s.sub_trxn_type='FS') end))
                         AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE s.sch_code=ANY(systematic.schemes) END
                         AND  cs.div_reinv_flag=ANY(systematic.inv_options)
                         AND s.cease_dt IS NULL AND s.cancellation_request_date IS NULL AND s.to_date IS NOT NULL AND s.to_date > NOW());
           end if;
       end if;
       raise notice '11. sip_uuids: %',cardinality(sip_uuids);
       if(systematic.plan @> ARRAY['DTP']) then
           if(systematic.inv_options = all_inv_check) then
               dtp_uuids := ARRAY(
                       SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                              INNER JOIN sphmf.DTP_REGN dr on dim.folio_number = dr.folio_no and dim.arn_code = dr.brok_code
                                                              INNER JOIN scheme_master sm ON dr.source_sch = sm.scheme_cd AND sm.allow_broker = allowbroker
                       WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                         AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE dr.source_sch=ANY(systematic.schemes) END
                         AND (CEASE_DATE IS NULL));
           else dtp_uuids := ARRAY(
                   SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                          INNER JOIN sphmf.DTP_REGN dr on dim.folio_number = dr.folio_no and dim.arn_code = dr.brok_code
                                                          INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = dr.SOURCE_SCH AND cs.folio_no=dr.folio_no
                                                          INNER JOIN scheme_master sm ON dr.source_sch = sm.scheme_cd AND sm.allow_broker = allowbroker
                   WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                     AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE dr.source_sch=ANY(systematic.schemes) END
                     AND cs.div_reinv_flag=ANY(systematic.inv_options)
                     AND (CEASE_DATE IS NULL));
           end if;
       end if;
       raise notice '12. dtp_uuids: %',cardinality(dtp_uuids);
       if(systematic.plan @> ARRAY['FLEXINDEX']) then
           if(systematic.inv_options = all_inv_check) then
               flexindex_uuids := ARRAY(
                       SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                              INNER JOIN sphmf.TRIGGER_TRXN tx on dim.folio_number = tx.folio_no and dim.arn_code = tx.brokcode
                                                              INNER JOIN scheme_master sm ON tx.schcode = sm.scheme_cd AND sm.allow_broker = allowbroker
                       WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                         AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE tx.schcode=ANY(systematic.schemes) END
                         AND PERCENT_OF IS NOT NULL
                         AND cease_date IS NULL AND DATE_OF_EXEC IS NULL);
           else
               flexindex_uuids := ARRAY(
                       SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                              INNER JOIN sphmf.TRIGGER_TRXN tx on dim.folio_number = tx.folio_no and dim.arn_code = tx.brokcode
                                                              INNER JOIN sphmf.customer_schemes cs ON cs.sch_code = tx.schcode AND cs.folio_no=tx.folio_no
                                                              INNER JOIN scheme_master sm ON tx.schcode = sm.scheme_cd AND sm.allow_broker = allowbroker
                       WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                         AND CASE WHEN systematic.schemes @> all_check THEN TRUE ELSE tx.schcode=ANY(systematic.schemes) END
                         AND cs.div_reinv_flag=ANY(systematic.inv_options)
                         AND PERCENT_OF IS NOT NULL
                         AND cease_date IS NULL AND DATE_OF_EXEC IS NULL);
           end if;
       end if;
       raise notice '13. flexindex_uuids: %',cardinality(flexindex_uuids);
       sys_uuids := sip_uuids || dtp_uuids || flexindex_uuids;
       if systematic.is_active = 'false' then
           uuids := array_subtract(uuids, sys_uuids);
       else
           uuids := sys_uuids;
       end if;
   end if;
   raise notice '14. uuids: %',cardinality(uuids);
   if cardinality(uuids) > 0 and (activity.have != 'ALL') then
       activity_uuids := ARRAY(
               SELECT distinct investor_uuid FROM distributor_investor_mapping dim
                                                      INNER JOIN sphmf.processed_trxns pt ON dim.folio_number = pt.folio_no and dim.arn_code = pt.broker_code
                                                      INNER JOIN sphmf.customer_schemes cs ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code
                                                      INNER JOIN scheme_master sm ON pt.sch_code = sm.scheme_cd AND sm.allow_broker = allowbroker
                                                      INNER JOIN sphmf.transaction_types tt ON tt.trxntypcod= pt.trxn_type_code
               WHERE dim.arn_code = arnCode and dim.investor_uuid=ANY(uuids)
                 AND ((case when (activity.activity_type @> ARRAY['DTP']) then (tt.trxndbcr = 'DR' AND trxn_type_code ='DRDTP') end) or
                      (case when (activity.activity_type @> ARRAY['PURCHASE']) then (pt.trxn_subtype_code='N') AND tt.trxndbcr = 'P' end) or
                      (case when (activity.activity_type @> ARRAY['SWITCH']) then (pt.trxn_subtype_code='N') AND tt.trxndbcr IN ('SI','SO') end) or
                      (case when (activity.activity_type @> ARRAY['REDEMPTION']) then (pt.trxn_subtype_code='N') AND tt.trxndbcr = 'R' end) or
                      (case when (activity.activity_type @> ARRAY['SIP']) then (pt.trxn_subtype_code='S') AND tt.trxndbcr = 'P' end) or
                      (case when (activity.activity_type @> ARRAY['STP']) then (pt.trxn_subtype_code='S') AND tt.trxndbcr IN ('SI','SO') end) or
                      (case when (activity.activity_type @> ARRAY['SWP']) then (pt.trxn_subtype_code='S') AND tt.trxndbcr = 'R' end) or
                      (case when activity.activity_type @> ARRAY['FLEXSIP'] then (pt.trxn_subtype_code = 'FS' AND tt.trxndbcr='P') end))
                 AND CASE WHEN activity.schemes @> all_check THEN TRUE ELSE pt.sch_code=ANY(activity.schemes) END
                 AND CASE WHEN activity.inv_options @> all_check THEN TRUE ELSE cs.div_reinv_flag=ANY(activity.inv_options) END
                 AND pt.entry_date >= now() - (activity.duration)::INTERVAL);
       raise notice '15. activity_uuids: %',cardinality(activity_uuids);
       if activity.have = 'false' then
           uuids := array_subtract(uuids, activity_uuids);
       else
           uuids := activity_uuids;
       end if;
   end if;
   raise notice '16. uuids: %',cardinality(uuids);
   uuids := ARRAY(select distinct i.uuid  FROM investor i
                  where i.uuid=ANY(uuids) AND (case when searchText <> '' then lower(i.first_name) ILIKE searchText else true end));
   if(sortValue = 'DESC') then
       return query
           select distinct i.uuid::varchar, trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')),
                                                        ltrim(concat(nullif(i.middle_name, NULL), ' ')),
                                                        ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.pan_number, i.dob, i.email, i.mobile_number, cardinality(uuids),
                           CASE WHEN sortKey = 'pan_number' THEN i.pan_number
                                WHEN sortKey = 'dob' THEN i.dob::varchar
                                ELSE first_name END
           FROM investor i
           where i.uuid=ANY(uuids)
           ORDER BY CASE
                        WHEN sortKey = 'pan_number' THEN i.pan_number
                        WHEN sortKey = 'dob' THEN i.dob::varchar
                        ELSE first_name END
                   DESC limit pageLimit offset pageIndex;
   else
       return query
           select distinct i.uuid::varchar, trim(concat(ltrim(concat(nullif(i.first_name, NULL), ' ')),
                                                        ltrim(concat(nullif(i.middle_name, NULL), ' ')),
                                                        ltrim(concat(nullif(i.last_name, NULL), ' ')))) first_name, i.pan_number, i.dob, i.email, i.mobile_number, cardinality(uuids),
                           CASE WHEN sortKey = 'pan_number' THEN i.pan_number
                                WHEN sortKey = 'dob' THEN i.dob::varchar
                                ELSE first_name END
           FROM investor i
           where i.uuid=ANY(uuids)
           ORDER BY CASE
                        WHEN sortKey = 'pan_number' THEN i.pan_number
                        WHEN sortKey = 'dob' THEN i.dob::varchar
                        ELSE first_name END
                   ASC limit pageLimit offset pageIndex;
   end if;
END
$function$
;

