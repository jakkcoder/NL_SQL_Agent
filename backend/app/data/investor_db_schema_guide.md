# Investor warehouse schema guide

Generated: 2026-05-21T11:07:53.493650+00:00
Source contract: 2026-05-21T10:02:55.644048+00:00

Compact natural-language schema for LLM read-only SQL generation. Each table includes a sample_row (first DB record, documented columns only) so you can see value formats. Only documented columns may be referenced in SQL.

## SQL rules

- **read_only**: Single SELECT or WITH…SELECT; LIMIT <= 500.
- **parameters**: Use %s placeholders only; first parameter is session_arn.
- **arn_scope**: Always filter via public.distributor_investor_mapping.arn_code = %s.
- **identifiers**: Use only tables/columns listed under tables[].columns in this guide.
- **joins**: Prefer join_recipes; match folio_no/folio_number and sch_code/scheme_cd consistently.
- **advanced**: Use EXISTS subqueries for holdings/activity/SIP filters; AGE(dob) for age; ILIKE for city; aggregate HAVING for unit balances.

## Join recipes

### arn_scope_anchor
Every query must scope to the session distributor ARN.
```sql
public.distributor_investor_mapping dim WHERE dim.arn_code = %s
```

### investor_identity
List investors for an ARN.
```sql
dim.investor_uuid = public.investor.uuid AND dim.arn_code = %s
```

### folio_kyc_city
Geography / email / folio-level attributes (e.g. Mumbai).
```sql
sphmf.customer_master cm ON cm.folio_no = dim.folio_number WHERE dim.arn_code = %s AND lower(trim(cm.city::text)) ILIKE %s
```

### otm_bank
One-time mandate (OTM) via bank registration.
```sql
sphmf.multiple_bank mb ON mb.folio_no = dim.folio_number JOIN public.payout_mechanism pm ON mb.paymech = pm.pay_mech WHERE pm.otm_flag IS TRUE AND mb.om_umrn IS NOT NULL
```

### holdings_units
Positive unit balance (holdings) by scheme.
```sql
sphmf.processed_trxns pt JOIN sphmf.customer_schemes cs ON pt.folio_no = cs.folio_no AND pt.sch_code = cs.sch_code JOIN public.scheme_master sm ON pt.sch_code = sm.scheme_cd WHERE pt.broker_code = %s GROUP BY pt.folio_no, pt.sch_code HAVING SUM(signed units) > 0
```

### active_sipstp
Active systematic plans (SIP/STP/SWP families).
```sql
sphmf.sipstp s ON dim.folio_number = s.folio_no AND dim.arn_code = s.brok_code JOIN public.scheme_master sm ON s.sch_code = sm.scheme_cd WHERE s.cease_dt IS NULL AND s.to_date > NOW()
```

### investor_activity
Purchases/redemptions/SIP/STP over a time window.
```sql
sphmf.processed_trxns pt JOIN sphmf.transaction_types tt ON pt.trxn_type = tt.trxn_type_code WHERE pt.broker_code = %s AND pt.l_trxn_date >= %s
```

### minor_tax_status
Minor investor subtype via tax status flags.
```sql
sphmf.customer_master cm JOIN public.tax_status ts ON cm.inv_type = ts.inv_type_code WHERE ts.minor_flag = 'Y' AND ts.distributor_flag = 'Y'
```

### cgf_schemes
Capital gains feeder (CGF) scheme filter.
```sql
sphmf.scheme_setup WHERE cgf_flag = 'C' AND plan_type <> 'D'
```

## Tables

### `public.distributor_investor_mapping`
Bridge table: links distributor ARN (arn_code) to investor UUID and folio_number. Use as the mandatory ARN scope anchor for every query.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `arn_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `folio_number` | character varying | YES | folio identifier linking sphmf and public schemas; character varying nullable |
| `investor_uuid` | uuid | YES | investor UUID key; uuid nullable |
| `pan_number` | character varying | NO | PAN tax id; character varying |
| `uuid` | uuid | NO | investor UUID key; uuid |
| `created_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `marketing_subscription` | boolean | NO | boolean |
| `whatsapp_notifications` | boolean | NO | boolean |
| `whatsapp_subscription` | boolean | YES | boolean nullable |

**Sample row (first record, documented columns):**

```json
{
  "arn_code": "ARN-104355",
  "folio_number": "16900093",
  "investor_uuid": "5f4992ac-278e-4fc1-860a-3be27150548a",
  "pan_number": "DCYPK0590N",
  "uuid": "dbb7613b-d57a-4358-84f6-90a3f2b3281b",
  "created_date": null,
  "marketing_subscription": true,
  "whatsapp_notifications": true,
  "whatsapp_subscription": false
}
```

### `public.investor`
Investor master: legal name, PAN, date of birth, email, mobile. Join via uuid = distributor_investor_mapping.investor_uuid.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `dob` | date | YES | date of birth; use AGE(dob) for age filters; date nullable |
| `email` | character varying | YES | email address; character varying nullable |
| `first_name` | character varying | YES | character varying nullable |
| `last_name` | character varying | YES | character varying nullable |
| `middle_name` | character varying | YES | character varying nullable |
| `mobile_number` | character varying | YES | character varying nullable |
| `pan_number` | character varying | YES | PAN tax id; character varying nullable |
| `uuid` | uuid | NO | investor UUID key; uuid |
| `created_time` | timestamp without time zone | YES | timestamp without time zone nullable |
| `is_mobile_active` | boolean | NO | boolean |
| `is_pan_aadhar_linked` | character varying | YES | PAN tax id; character varying nullable |

**Sample row (first record, documented columns):**

```json
{
  "dob": "1981-06-29",
  "email": "SAURABH.JAIN.29@GMAIL.COM",
  "first_name": "SAURABH DEVENDRA JAIN",
  "last_name": null,
  "middle_name": null,
  "mobile_number": "9869279902",
  "pan_number": "AEBPJ7885D",
  "uuid": "dc53aaee-139f-4fba-b3a7-3752b9923b92",
  "created_time": "2021-03-17T05:52:30.627",
  "is_mobile_active": true,
  "is_pan_aadhar_linked": null
}
```

### `public.tax_status`
Lookup for investor type codes (inv_type_code) with minor/distributor/active flags.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `active_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `distributor_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `minor_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `add_bank_cheque_leaf_enabled` | boolean | YES | boolean nullable |
| `banned_investors_flag` | boolean | YES | boolean/char flag; boolean nullable |
| `check_fatca` | character varying | YES | character varying nullable |
| `cobm_enabled` | boolean | YES | boolean nullable |
| `concat_updation_enable` | character varying | YES | character varying nullable |
| `corporate_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `created_date` | date | YES | date/timestamp; date nullable |
| `created_time` | timestamp without time zone | YES | timestamp without time zone nullable |
| `div_status_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `emandate_enabled` | boolean | YES | boolean nullable |
| `folio_creation_enabled` | boolean | YES | folio identifier linking sphmf and public schemas; boolean nullable |
| `form15gh_applicable` | boolean | YES | boolean nullable |
| `id` | uuid | NO | uuid |
| `individual_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `inv_type_code` | character varying | YES | code lookup key; character varying nullable |
| `inv_type_desc` | character varying | YES | character varying nullable |
| `investor_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `minor` | character varying | YES | character varying nullable |
| `nominee` | character varying | YES | character varying nullable |
| `nri_nre` | character varying | YES | character varying nullable |
| `quick_investment_enabled` | boolean | YES | boolean nullable |
| `retirement_scheme_enable` | character varying | YES | character varying nullable |
| `ubo_enabled` | character varying | YES | character varying nullable |
| `update_contact_detail` | boolean | YES | boolean nullable |

**Sample row (first record, documented columns):**

```json
{
  "active_flag": "Y",
  "distributor_flag": "Y",
  "minor_flag": "N",
  "add_bank_cheque_leaf_enabled": true,
  "banned_investors_flag": true,
  "check_fatca": "N",
  "cobm_enabled": true,
  "concat_updation_enable": "Y",
  "corporate_flag": null,
  "created_date": null,
  "created_time": null,
  "div_status_flag": null,
  "emandate_enabled": false,
  "folio_creation_enabled": true,
  "form15gh_applicable": false,
  "id": "dde164f0-7a69-4f75-9b2f-7556360f0f81",
  "individual_flag": "Y",
  "inv_type_code": "70",
  "inv_type_desc": "Person of Indian Origin [PIO]",
  "investor_flag": "Y",
  "minor": null,
  "nominee": null,
  "nri_nre": "Y",
  "quick_investment_enabled": true,
  "retirement_scheme_enable": "Y",
  "ubo_enabled": "N",
  "update_contact_detail": true
}
```

### `public.scheme_master`
Scheme reference (scheme_cd, scheme_name, allow_broker). Join on sch_code = scheme_cd.
*(Showing 22 of 205 columns.)*

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `active_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `allow_broker` | character varying | YES | character varying nullable |
| `fund_code` | character varying | YES | code lookup key; character varying nullable |
| `investment_option` | character varying | YES | character varying nullable |
| `scheme_cd` | character varying | YES | mutual fund scheme code (join to scheme_master.scheme_cd); character varying nullable |
| `scheme_name` | character varying | YES | character varying nullable |
| `scheme_type` | character varying | YES | character varying nullable |
| `approved_by` | character varying | YES | character varying nullable |
| `approved_dt` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `approved_note` | character varying | YES | character varying nullable |
| `cgf_applicable` | boolean | YES | boolean nullable |
| `clone_scheme_cd` | character varying | YES | character varying nullable |
| `created_by` | character varying | YES | character varying nullable |
| `created_dt` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `dividend_payout_applicable` | boolean | YES | boolean nullable |
| `dividend_reinvestment_applicable` | boolean | YES | boolean nullable |
| `document_required` | character varying | YES | character varying nullable |
| `document_type` | character varying | YES | character varying nullable |
| `dp_active` | character varying | YES | character varying nullable |
| `dtp_source_enabled` | character varying | YES | character varying nullable |
| `dtp_target_enabled` | character varying | YES | character varying nullable |
| `fatf_investor` | character varying | YES | character varying nullable |

**Sample row (first record, documented columns):**

```json
{
  "active_flag": "Y",
  "allow_broker": "Y",
  "fund_code": "HCPROSEP13",
  "investment_option": "Growth",
  "scheme_cd": "CP2GR",
  "scheme_name": "HDFC CPO 36M September 2013 - Series I - Growth",
  "scheme_type": "DEBT",
  "approved_by": "NEHALG",
  "approved_dt": "2016-10-19T00:00:00",
  "approved_note": null,
  "cgf_applicable": false,
  "clone_scheme_cd": null,
  "created_by": "troy",
  "created_dt": "2013-09-13T00:00:00",
  "dividend_payout_applicable": false,
  "dividend_reinvestment_applicable": false,
  "document_required": "N",
  "document_type": null,
  "dp_active": "N",
  "dtp_source_enabled": "N",
  "dtp_target_enabled": "N",
  "fatf_investor": "N"
}
```

### `public.payout_mechanism`
Payment mechanism lookup; filter OTM-capable pay_mech rows (otm_flag, active_flag).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `active_flag` | boolean | NO | boolean/char flag; boolean |
| `otm_flag` | boolean | NO | boolean/char flag; boolean |
| `created_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `id` | uuid | NO | uuid |
| `pay_mech` | character varying | YES | character varying nullable |

**Sample row (first record, documented columns):**

```json
{
  "active_flag": true,
  "otm_flag": true,
  "created_date": "2020-08-31T09:42:40.841376",
  "id": "67ac458e-46c6-4dc7-8220-1b97146ed695",
  "pay_mech": "OTM"
}
```

### `sphmf.customer_master`
Folio-level customer/KYC: city, inv_type, names. Join folio_no = dim.folio_number.
*(Showing 45 of 74 columns.)*

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `city` | character varying | YES | city name for geography filters (e.g. Mumbai); character varying nullable |
| `email` | character varying | YES | email address; character varying nullable |
| `first_name` | character varying | NO | character varying |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `inv_type` | character varying | NO | investor type code (join tax_status); character varying |
| `last_name` | character varying | YES | character varying nullable |
| `middle_name` | character varying | YES | character varying nullable |
| `address1` | character varying | YES | character varying nullable |
| `address2` | character varying | YES | character varying nullable |
| `address3` | character varying | YES | character varying nullable |
| `alternate_folio_no` | numeric | YES | folio identifier linking sphmf and public schemas; numeric nullable |
| `application_no` | character varying | YES | character varying nullable |
| `aslstatus` | character | YES | character nullable |
| `birth_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `br_recddt` | timestamp without time zone | YES | timestamp without time zone nullable |
| `chk_digit` | character varying | YES | character varying nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `contact_person` | character varying | YES | character varying nullable |
| `country` | character varying | YES | character varying nullable |
| `dp_id` | character varying | YES | character varying nullable |
| `email_flg` | character varying | YES | email address; character varying nullable |
| `email_valid` | character | YES | email address; character nullable |
| `exchid1` | character varying | YES | character varying nullable |
| `exchid2` | character varying | YES | character varying nullable |
| `father_name` | character varying | YES | character varying nullable |
| `fh_ckyc_no` | character varying | YES | character varying nullable |
| `fh_kyc` | numeric | YES | numeric nullable |
| `fh_kyc_type` | character | YES | character nullable |
| `folio_create_date` | timestamp without time zone | YES | folio identifier linking sphmf and public schemas; timestamp without time zone nullable |
| `folio_lock_reason` | character varying | YES | folio identifier linking sphmf and public schemas; character varying nullable |
| `folio_lock_reason_codes` | character varying | YES | folio identifier linking sphmf and public schemas; character varying nullable |
| `g_ckyc_no` | character varying | YES | character varying nullable |
| `g_kyc_type` | character | YES | character nullable |
| `gdate_of_birth` | timestamp without time zone | YES | timestamp without time zone nullable |
| `gender` | character varying | YES | character varying nullable |
| `gpan_no` | character varying | YES | PAN tax id; character varying nullable |
| `guar_kyc` | numeric | YES | numeric nullable |
| `guardian_gender` | character | YES | character nullable |
| `guardian_name` | character varying | YES | character varying nullable |
| `guardian_pan_exem_category` | character varying | YES | PAN tax id; character varying nullable |
| `guardian_pan_exem_ref_no` | character varying | YES | PAN tax id; character varying nullable |
| `guardian_relationship` | character varying | YES | character varying nullable |
| `gvalid_pan` | character | YES | PAN tax id; character nullable |
| `insurance_id` | numeric | YES | numeric nullable |
| `insurance_tag` | character | YES | character nullable |

**Sample row (first record, documented columns):**

```json
{
  "city": "BIRBHUM",
  "email": "ghoshchandan19@gmail.com",
  "first_name": "CHANDAN",
  "folio_no": "14428383",
  "inv_type": "01",
  "last_name": "GHOSH",
  "middle_name": null,
  "address1": "C/O SAILENDRA NATH GHOSH,GRAM LAUBERIA(EAST) PART",
  "address2": "LAUBERIA(PART),NEAR KALI MANDIR,LAUBERE,BIRBHUM,WEST",
  "address3": "BENGAL,731125",
  "alternate_folio_no": null,
  "application_no": null,
  "aslstatus": null,
  "birth_date": "1991-02-18T00:00:00",
  "br_recddt": null,
  "chk_digit": "34",
  "commit_scn": 10562307388099,
  "contact_person": null,
  "country": "101",
  "dp_id": null,
  "email_flg": "E",
  "email_valid": "Y",
  "exchid1": null,
  "exchid2": null,
  "father_name": null,
  "fh_ckyc_no": null,
  "fh_kyc": null,
  "fh_kyc_type": null,
  "folio_create_date": "2023-10-04T00:00:00",
  "folio_lock_reason": null,
  "folio_lock_reason_codes": null,
  "g_ckyc_no": null,
  "g_kyc_type": null,
  "gdate_of_birth": null,
  "gender": null,
  "gpan_no": null,
  "guar_kyc": 1,
  "guardian_gender": null,
  "guardian_name": null,
  "guardian_pan_exem_category": null,
  "guardian_pan_exem_ref_no": null,
  "guardian_relationship": null,
  "gvalid_pan": null,
  "insurance_id": null,
  "insurance_tag": null
}
```

### `sphmf.multiple_bank`
Bank/mandate rows per folio (folio_no); used for OTM (om_umrn, paymech, cease_dt).
*(Showing 45 of 50 columns.)*

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `broker_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `cease_dt` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `city` | character varying | YES | city name for geography filters (e.g. Mumbai); character varying nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `om_umrn` | character varying | YES | OTM UMRN registration; character varying nullable |
| `paymech` | character varying | YES | payment mechanism code (join payout_mechanism); character varying nullable |
| `ac_no` | character varying | YES | character varying nullable |
| `ac_type` | character varying | YES | character varying nullable |
| `acno_valid` | character varying | YES | character varying nullable |
| `ae_code` | character varying | YES | code lookup key; character varying nullable |
| `arn_emp_code` | character varying | YES | code lookup key; character varying nullable |
| `bank_country` | character varying | YES | character varying nullable |
| `bank_micr` | character varying | YES | character varying nullable |
| `bank_name` | character varying | YES | character varying nullable |
| `bank_pincode` | character varying | YES | character varying nullable |
| `bank_state` | character varying | YES | character varying nullable |
| `bank_swft` | character varying | YES | character varying nullable |
| `bkadd1` | character varying | YES | character varying nullable |
| `bkadd2` | character varying | YES | character varying nullable |
| `bkadd3` | character varying | YES | character varying nullable |
| `branch_name` | character varying | YES | character varying nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `debit_type` | character varying | YES | character varying nullable |
| `euin_opted` | character | YES | character nullable |
| `identifier` | numeric | NO | numeric |
| `ifsccode` | character varying | YES | character varying nullable |
| `imps_ac_verified` | character | YES | character nullable |
| `micr_code` | character varying | YES | code lookup key; character varying nullable |
| `minor_bank_whitelist_flag` | character | YES | boolean/char flag; character nullable |
| `mobile_no` | character varying | YES | character varying nullable |
| `neftcode` | character varying | YES | character varying nullable |
| `om_expiry_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `om_expiry_date_n` | timestamp with time zone | YES | timestamp with time zone nullable |
| `om_max_amount` | numeric | YES | numeric nullable |
| `om_max_amount_n` | numeric | YES | numeric nullable |
| `om_pref_open_mandate` | character | YES | character nullable |
| `om_reg_confirm_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `om_regn_mode` | character varying | YES | character varying nullable |
| `om_start_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `om_start_date_n` | timestamp with time zone | YES | timestamp with time zone nullable |
| `om_status` | character | YES | character nullable |
| `om_status_old` | character | YES | character nullable |
| `otm_frequency` | character varying | YES | character varying nullable |
| `payout_purpose` | character | YES | character nullable |
| `regn_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |

**Sample row (first record, documented columns):**

```json
{
  "broker_code": null,
  "cease_dt": null,
  "city": "MUMBAI",
  "folio_no": "14420488",
  "om_umrn": "UMRN123456789",
  "paymech": "NACH",
  "ac_no": "123456789012",
  "ac_type": "SB",
  "acno_valid": null,
  "ae_code": null,
  "arn_emp_code": null,
  "bank_country": null,
  "bank_micr": null,
  "bank_name": "HDFC BANK",
  "bank_pincode": null,
  "bank_state": null,
  "bank_swft": null,
  "bkadd1": null,
  "bkadd2": null,
  "bkadd3": null,
  "branch_name": "MUMBAI MAIN",
  "commit_scn": null,
  "debit_type": null,
  "euin_opted": null,
  "identifier": 9362714,
  "ifsccode": "HDFC0001234",
  "imps_ac_verified": null,
  "micr_code": null,
  "minor_bank_whitelist_flag": null,
  "mobile_no": null,
  "neftcode": null,
  "om_expiry_date": "2027-04-15T09:42:19.554291+00:00",
  "om_expiry_date_n": null,
  "om_max_amount": 100000.0,
  "om_max_amount_n": null,
  "om_pref_open_mandate": null,
  "om_reg_confirm_date": null,
  "om_regn_mode": "ONLINE",
  "om_start_date": "2026-04-15T09:42:19.554291+00:00",
  "om_start_date_n": null,
  "om_status": "A",
  "om_status_old": null,
  "otm_frequency": "MONTHLY",
  "payout_purpose": null,
  "regn_date": "2026-04-15T09:42:19.554291+00:00"
}
```

### `sphmf.customer_schemes`
Folio + scheme registration (folio_no, sch_code, div_reinv_flag, l_trxn_date).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `broker_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `div_reinv_flag` | character | YES | boolean/char flag; character nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `l_trxn_date` | timestamp without time zone | YES | last transaction date for activity/dormancy windows; timestamp without time zone nullable |
| `sch_code` | character varying | NO | mutual fund scheme code (join to scheme_master.scheme_cd); character varying |
| `acno_valid` | character varying | YES | character varying nullable |
| `bank_ac_no` | character varying | YES | character varying nullable |
| `bank_ac_type` | character varying | YES | character varying nullable |
| `bank_branch` | character varying | YES | character varying nullable |
| `bank_city` | character varying | YES | character varying nullable |
| `bank_name` | character varying | YES | character varying nullable |
| `bank_pincode` | character varying | YES | character varying nullable |
| `clos_bal_hold` | numeric | YES | numeric nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `create_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `div_pay_mode` | character varying | YES | character varying nullable |
| `ecs_no` | character varying | YES | character varying nullable |
| `ecs_no_old` | numeric | YES | numeric nullable |
| `ecsvalid` | character varying | YES | character varying nullable |
| `exchange_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `hold_mode_code` | character varying | YES | code lookup key; character varying nullable |
| `ifsccode` | character varying | YES | character varying nullable |
| `ifscvalid` | character varying | YES | character varying nullable |
| `imps_ac_verified` | character | YES | character nullable |
| `minor_bank_whitelist_flag` | character | YES | boolean/char flag; character nullable |
| `neftcode` | character varying | YES | character varying nullable |
| `pledged` | numeric | YES | numeric nullable |
| `redeem_div` | character | YES | character nullable |
| `redem_pay_mode` | character varying | YES | character varying nullable |
| `sub_broker_code` | character varying | YES | code lookup key; character varying nullable |
| `time_stamp` | timestamp without time zone | YES | timestamp without time zone nullable |
| `total_units` | numeric | YES | numeric nullable |
| `update_serial` | numeric | YES | numeric nullable |

**Sample row (first record, documented columns):**

```json
{
  "broker_code": "ARN-4279",
  "div_reinv_flag": "Z",
  "folio_no": "20608729",
  "l_trxn_date": "2025-07-16T00:00:00",
  "sch_code": "GFG",
  "acno_valid": "V",
  "bank_ac_no": "919010029464467",
  "bank_ac_type": "SB",
  "bank_branch": null,
  "bank_city": "MUMBAI",
  "bank_name": "AXIS BANK LTD",
  "bank_pincode": null,
  "clos_bal_hold": 0.0,
  "commit_scn": 11042579808633,
  "create_date": "2025-01-16T00:00:00",
  "div_pay_mode": "NEFT",
  "ecs_no": null,
  "ecs_no_old": null,
  "ecsvalid": null,
  "exchange_flag": null,
  "hold_mode_code": "SI",
  "ifsccode": "UTIB0002982",
  "ifscvalid": null,
  "imps_ac_verified": "Y",
  "minor_bank_whitelist_flag": null,
  "neftcode": "UTIB0002982",
  "pledged": 0.0,
  "redeem_div": null,
  "redem_pay_mode": "NEFT",
  "sub_broker_code": null,
  "time_stamp": "2025-07-17T03:42:59",
  "total_units": 152.936,
  "update_serial": null
}
```

### `sphmf.scheme_setup`
Scheme setup flags (schcode, cgf_flag, plan_type) for CGF and plan filters.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `cgf_flag` | character | NO | boolean/char flag; character |
| `plan_type` | character | YES | character nullable |
| `schcode` | character varying | NO | mutual fund scheme code (join to scheme_master.scheme_cd); character varying |
| `allot_dt` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `asset_class` | character varying | YES | character varying nullable |
| `close_dt` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `link_scheme_code` | character varying | YES | code lookup key; character varying nullable |
| `lockdate` | timestamp with time zone | YES | timestamp with time zone nullable |
| `maturity_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `maturity_flag` | character | YES | boolean/char flag; character nullable |
| `open_dt` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `scheme_cusip_no` | character varying | YES | character varying nullable |
| `scheme_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `scheme_type` | character varying | YES | character varying nullable |
| `schname` | character varying | NO | character varying |
| `short_name` | character varying | YES | character varying nullable |
| `sub_fund_flag` | character | YES | boolean/char flag; character nullable |
| `subfundc` | character varying | YES | character varying nullable |
| `time_stamp` | timestamp with time zone | YES | timestamp with time zone nullable |

**Sample row (first record, documented columns):**

```json
{
  "cgf_flag": "N",
  "plan_type": "R",
  "schcode": "BFD",
  "allot_dt": "2000-07-20T00:00:00+00:00",
  "asset_class": "EQUITY",
  "close_dt": "2999-12-31T00:00:00+00:00",
  "commit_scn": null,
  "link_scheme_code": null,
  "lockdate": "2000-09-11T00:00:00+00:00",
  "maturity_date": null,
  "maturity_flag": "N",
  "open_dt": "2000-09-11T00:00:00+00:00",
  "scheme_cusip_no": "1005",
  "scheme_flag": "O",
  "scheme_type": "Balanced",
  "schname": "HDFC Balanced Fund - Regular Plan - Dividend ",
  "short_name": "HDFC Balanced Fund-Dividend",
  "sub_fund_flag": "Y",
  "subfundc": "PMC",
  "time_stamp": null
}
```

### `sphmf.processed_trxns`
Posted transactions: units, trxn_sign, sch_code, broker_code, l_trxn_date, trxn_type.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `broker_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `sch_code` | character varying | NO | mutual fund scheme code (join to scheme_master.scheme_cd); character varying |
| `trxn_sign` | character | YES | transaction sign (+ purchase / - redemption) for unit balance; character nullable |
| `trxn_subtype_code` | character | NO | code lookup key; character |
| `trxn_type_code` | character varying | NO | code lookup key; character varying |
| `units` | numeric | NO | transaction units; numeric |
| `amc_comm` | numeric | YES | numeric nullable |
| `amount` | numeric | NO | numeric |
| `appl_no` | character varying | YES | character varying nullable |
| `arn_emp_code` | character varying | YES | code lookup key; character varying nullable |
| `atrxn_no` | numeric | YES | numeric nullable |
| `branch_code` | character varying | YES | code lookup key; character varying nullable |
| `brok_comm` | numeric | YES | numeric nullable |
| `brok_dlr_comm_paid` | character | YES | character nullable |
| `brok_perc` | numeric | YES | numeric nullable |
| `collection_bank_code` | character varying | NO | code lookup key; character varying |
| `commit_scn` | numeric | YES | numeric nullable |
| `eisc_trxn_no` | numeric | NO | numeric |
| `entry_date` | timestamp with time zone | NO | date/timestamp; timestamp with time zone |
| `euin_opted` | character | YES | character nullable |
| `euin_valid` | character | YES | character nullable |
| `old_scheme_code` | character varying | NO | code lookup key; character varying |
| `plot_amount` | numeric | NO | numeric |
| `prev_folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `price` | numeric | YES | numeric nullable |
| `process_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `purch_id` | numeric | NO | numeric |
| `remarks` | character varying | YES | character varying nullable |
| `source` | character varying | YES | character varying nullable |
| `source_broker_type` | character | YES | character nullable |
| `stt_tax` | numeric | YES | numeric nullable |
| `sub_broker_arn` | character varying | YES | character varying nullable |
| `subbroker_code` | character varying | YES | code lookup key; character varying nullable |
| `tax` | numeric | YES | numeric nullable |
| `ter_location` | character | YES | character nullable |
| `time_stamp` | timestamp with time zone | YES | timestamp with time zone nullable |
| `total_tax` | numeric | YES | numeric nullable |
| `trxn_date` | timestamp with time zone | NO | date/timestamp; timestamp with time zone |
| `trxn_no` | numeric | NO | numeric |
| `trxn_status` | character varying | YES | character varying nullable |
| `trxn_type_flag` | character varying | YES | boolean/char flag; character varying nullable |
| `update_serial` | numeric | YES | numeric nullable |

**Sample row (first record, documented columns):**

```json
{
  "broker_code": "ARN-0411",
  "folio_no": "8829887",
  "sch_code": "MULG",
  "trxn_sign": "+",
  "trxn_subtype_code": "N",
  "trxn_type_code": "P43A",
  "units": 3702.543,
  "amc_comm": 0.0,
  "amount": 130000.0,
  "appl_no": null,
  "arn_emp_code": "E030803",
  "atrxn_no": null,
  "branch_code": "BKN151",
  "brok_comm": 0.0,
  "brok_dlr_comm_paid": "Y",
  "brok_perc": 0.0,
  "collection_bank_code": "CAMSSUDH",
  "commit_scn": null,
  "eisc_trxn_no": 8969712,
  "entry_date": "2023-12-28T12:25:46+00:00",
  "euin_opted": "Y",
  "euin_valid": "Y",
  "old_scheme_code": "MULG",
  "plot_amount": 130000.0,
  "prev_folio_no": "8829887",
  "price": 35.111,
  "process_date": "2022-10-05T12:25:46",
  "purch_id": 14677999507,
  "remarks": "<E/S:B>Transaction Received Between 2 P.M and 3 P.M$11/May/2018 16:35:28<MULTI INV TC CHECK UPDATED_ENTRY_DATE-11-May-2018 AND LOCATED ON 11-MAY-2018 16:47:4...",
  "source": "eISC",
  "source_broker_type": null,
  "stt_tax": 0.0,
  "sub_broker_arn": null,
  "subbroker_code": null,
  "tax": 0.0,
  "ter_location": "B",
  "time_stamp": null,
  "total_tax": 0.0,
  "trxn_date": "2022-10-05T12:25:46+00:00",
  "trxn_no": 142062039,
  "trxn_status": "N",
  "trxn_type_flag": "AP",
  "update_serial": null
}
```

### `sphmf.sipstp`
Systematic instructions (SIP/STP/SWP): atrxn_type, switch_flag, sch_code, brok_code, dates.
*(Showing 45 of 67 columns.)*

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `atrxn_type` | character varying | NO | systematic plan transaction type (SIP/STP/SWP logic); character varying |
| `brok_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `cancellation_request_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `cease_dt` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `sch_code` | character varying | NO | mutual fund scheme code (join to scheme_master.scheme_cd); character varying |
| `sub_trxn_type` | character varying | YES | character varying nullable |
| `switch_flag` | character | YES | boolean/char flag; character nullable |
| `to_date` | timestamp with time zone | NO | date/timestamp; timestamp with time zone |
| `ae_code` | character varying | YES | code lookup key; character varying nullable |
| `amc_ref_no` | character varying | YES | character varying nullable |
| `amc_ter_mis_location_code` | character varying | YES | code lookup key; character varying nullable |
| `amount` | numeric | YES | numeric nullable |
| `appl_no` | character varying | YES | character varying nullable |
| `arn_emp_code` | character varying | YES | code lookup key; character varying nullable |
| `atrxn_no` | numeric | NO | numeric |
| `cams_om_mandate_id_no` | character varying | YES | character varying nullable |
| `camsom_no` | character varying | YES | character varying nullable |
| `cease_initiated_by` | character | YES | character nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `doc_no` | character varying | YES | character varying nullable |
| `entry_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `euin_opted` | character | YES | character nullable |
| `euin_valid` | character | YES | character nullable |
| `ext_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `first_trxn_with_sip` | character | YES | character nullable |
| `free_sip_target_scheme_code` | character varying | YES | code lookup key; character varying nullable |
| `frequency` | character varying | YES | character varying nullable |
| `from_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `gain_logic` | character | YES | character nullable |
| `gain_perc` | numeric | YES | numeric nullable |
| `gain_value` | character | YES | character nullable |
| `high_low` | character | YES | character nullable |
| `isip_status` | character | YES | character nullable |
| `location_code` | character varying | YES | code lookup key; character varying nullable |
| `mb_amount` | numeric | YES | numeric nullable |
| `mb_redemption_perc` | numeric | YES | numeric nullable |
| `mis_code` | character varying | YES | code lookup key; character varying nullable |
| `nigo_reason_code` | character varying | YES | code lookup key; character varying nullable |
| `no_of_instalments` | numeric | YES | numeric nullable |
| `old_auto_trxn_no` | numeric | YES | numeric nullable |
| `online_mode` | character varying | YES | character varying nullable |
| `package_name` | character varying | YES | character varying nullable |
| `pause_from_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |
| `pause_to_date` | timestamp with time zone | YES | date/timestamp; timestamp with time zone nullable |

**Sample row (first record, documented columns):**

```json
{
  "atrxn_type": "P",
  "brok_code": "ARN-0098",
  "cancellation_request_date": null,
  "cease_dt": null,
  "folio_no": "7248520",
  "sch_code": "32",
  "sub_trxn_type": null,
  "switch_flag": "X",
  "to_date": "0001-04-24T00:00:00+00:00 BC",
  "ae_code": "ARN-0098",
  "amc_ref_no": null,
  "amc_ter_mis_location_code": null,
  "amount": 3000.0,
  "appl_no": "201404230000001",
  "arn_emp_code": "E086797",
  "atrxn_no": 300041,
  "cams_om_mandate_id_no": null,
  "camsom_no": null,
  "cease_initiated_by": null,
  "commit_scn": null,
  "doc_no": null,
  "entry_date": "0001-04-23T00:00:00+00:00 BC",
  "euin_opted": "Y",
  "euin_valid": null,
  "ext_date": "0001-04-24T00:00:00+00:00 BC",
  "first_trxn_with_sip": null,
  "free_sip_target_scheme_code": null,
  "frequency": "OM",
  "from_date": "2016-11-15T00:00:00+00:00",
  "gain_logic": null,
  "gain_perc": 0.0,
  "gain_value": null,
  "high_low": null,
  "isip_status": null,
  "location_code": "NSEMFSS",
  "mb_amount": null,
  "mb_redemption_perc": null,
  "mis_code": null,
  "nigo_reason_code": null,
  "no_of_instalments": 12,
  "old_auto_trxn_no": null,
  "online_mode": null,
  "package_name": null,
  "pause_from_date": null,
  "pause_to_date": null
}
```

### `sphmf.dtp_regn`
Dynamic transfer plan (DTP) registrations.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `brok_code` | character varying | YES | distributor ARN / broker code for row scope; character varying nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `cease_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `created_authorized_by` | character varying | YES | character varying nullable |
| `editor_id` | character varying | YES | character varying nullable |
| `regn_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `reinvst_tag` | character | NO | character |
| `source_sch` | character varying | NO | character varying |
| `target_perc` | numeric | YES | numeric nullable |
| `target_sch` | character varying | NO | character varying |
| `time_stamp` | timestamp without time zone | YES | timestamp without time zone nullable |
| `user_id` | character varying | YES | character varying nullable |

**Sample row (first record, documented columns):**

```json
{
  "brok_code": "ARN-0411",
  "folio_no": "5245002",
  "cease_date": null,
  "commit_scn": 9727937008874.0,
  "created_authorized_by": null,
  "editor_id": null,
  "regn_date": "2020-05-22T00:00:00",
  "reinvst_tag": "Z",
  "source_sch": "LFDTN",
  "target_perc": 100.0,
  "target_sch": "AFRG",
  "time_stamp": "2020-05-22T12:14:41",
  "user_id": null
}
```

### `sphmf.trigger_trxn`
Trigger-based transaction rows.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `div_reinv_flag` | character | YES | boolean/char flag; character nullable |
| `folio_no` | character varying | NO | folio identifier linking sphmf and public schemas; character varying |
| `schcode` | character varying | NO | mutual fund scheme code (join to scheme_master.scheme_cd); character varying |
| `trxn_type_code` | character varying | NO | code lookup key; character varying |
| `units` | numeric | YES | transaction units; numeric nullable |
| `arn_emp_code` | character varying | YES | code lookup key; character varying nullable |
| `brokcode` | character varying | YES | character varying nullable |
| `cease_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `chk_digit` | character varying | YES | character varying nullable |
| `commence_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `commit_scn` | numeric | YES | numeric nullable |
| `date_of_exec` | timestamp without time zone | YES | timestamp without time zone nullable |
| `entry_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `euin_opted` | character | YES | character nullable |
| `euin_valid` | character | YES | character nullable |
| `event_no` | numeric | NO | numeric |
| `gain_or_value` | character | YES | character nullable |
| `high_or_low` | character | YES | character nullable |
| `last_alert_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `location_code` | character varying | YES | code lookup key; character varying nullable |
| `nav_high` | numeric | YES | numeric nullable |
| `nav_low` | numeric | YES | numeric nullable |
| `nav_perc` | numeric | YES | numeric nullable |
| `percent_of` | numeric | YES | numeric nullable |
| `price` | numeric | YES | numeric nullable |
| `reference_no` | numeric | YES | numeric nullable |
| `remarks` | character varying | YES | character varying nullable |
| `sensex_value` | numeric | YES | numeric nullable |
| `subbroker_code` | character varying | YES | code lookup key; character varying nullable |
| `tc_date` | timestamp without time zone | YES | date/timestamp; timestamp without time zone nullable |
| `time_stamp` | timestamp without time zone | YES | timestamp without time zone nullable |
| `toschcode` | character varying | YES | character varying nullable |
| `total_units` | character | YES | character nullable |
| `trig_logic` | character | YES | character nullable |
| `usercode` | character varying | YES | character varying nullable |
| `usertrxnno` | numeric | YES | numeric nullable |

**Sample row (first record, documented columns):**

```json
{
  "div_reinv_flag": "Z",
  "folio_no": "7629387",
  "schcode": "54",
  "trxn_type_code": "SO",
  "units": 0.0,
  "arn_emp_code": null,
  "brokcode": "ARN-7761",
  "cease_date": null,
  "chk_digit": "51",
  "commence_date": "2023-08-12T00:00:00",
  "commit_scn": null,
  "date_of_exec": null,
  "entry_date": "2022-09-24T00:00:00",
  "euin_opted": null,
  "euin_valid": null,
  "event_no": 46331,
  "gain_or_value": null,
  "high_or_low": null,
  "last_alert_date": null,
  "location_code": "755",
  "nav_high": null,
  "nav_low": null,
  "nav_perc": null,
  "percent_of": 30.0,
  "price": 50000.0,
  "reference_no": 4076,
  "remarks": " EBT Ceased - Not triggered for 365 days",
  "sensex_value": 7000.0,
  "subbroker_code": null,
  "tc_date": null,
  "time_stamp": null,
  "toschcode": "44",
  "total_units": null,
  "trig_logic": "E",
  "usercode": "CBE_ARUN",
  "usertrxnno": 134458
}
```

### `sphmf.transaction_types`
Maps trxn_type_code to trxndbcr / subtype for activity filters (purchase, redemption, SIP, etc.).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `trxndbcr` | character varying | NO | character varying |
| `commit_scn` | numeric | YES | numeric nullable |
| `face_value_flag` | character | YES | boolean/char flag; character nullable |
| `time_stamp` | timestamp without time zone | YES | timestamp without time zone nullable |
| `trxntypcod` | character varying | NO | character varying |
| `trxntypdes` | character varying | NO | character varying |

**Sample row (first record, documented columns):**

```json
{
  "trxndbcr": "P",
  "commit_scn": null,
  "face_value_flag": "N",
  "time_stamp": null,
  "trxntypcod": "PIXH",
  "trxntypdes": "NFO Purchase"
}
```
