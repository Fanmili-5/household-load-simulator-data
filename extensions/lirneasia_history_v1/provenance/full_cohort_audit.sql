SET memory_limit='2GB';
SET threads=4;
SET preserve_insertion_order=false;
CREATE TABLE raw AS SELECT household_ID AS id, try_cast(date||' '||time AS TIMESTAMP) AS dt,try_cast("importkwh(kwh)" AS DOUBLE) AS imp,try_cast("exportkwh(kwh)" AS DOUBLE) AS exp FROM read_csv('@RAW@/smart_15min_2.csv',all_varchar=true);
COPY (SELECT count(*) AS raw_rows,count(distinct id) households,min(dt) min_dt,max(dt) max_dt,count(*) FILTER(dt IS NULL) null_dt,count(*) FILTER(imp IS NULL OR NOT isfinite(imp)) invalid_import,count(*) FILTER(exp IS NULL OR NOT isfinite(exp)) invalid_export FROM raw) TO 'raw_counts.json' (FORMAT JSON,ARRAY true);
CREATE TABLE unique_points AS SELECT id,dt,count(*) n,min(imp) imp,min(exp) exp FROM raw WHERE dt IS NOT NULL GROUP BY id,dt;
COPY (SELECT count(*) unique_points,count(*) FILTER(n>1) duplicate_time_keys,sum(n-1) duplicate_extra_rows FROM unique_points) TO 'duplicate_counts.json' (FORMAT JSON,ARRAY true);
CREATE TABLE edges AS WITH a AS (SELECT *,lag(dt) OVER w prev_dt,lag(n) OVER w prev_n,lag(imp) OVER w prev_imp,lag(exp) OVER w prev_exp FROM unique_points WINDOW w AS (PARTITION BY id ORDER BY dt)) SELECT *,imp-prev_imp di,exp-prev_exp de,dt-INTERVAL 15 MINUTE t_start,n=1 AND prev_n=1 AND dt-prev_dt=INTERVAL 15 MINUTE AND isfinite(imp) AND isfinite(exp) AND isfinite(prev_imp) AND isfinite(prev_exp) AND imp>=prev_imp AND exp>=prev_exp AS valid FROM a;
COPY (SELECT count(*) FILTER(dt-prev_dt=INTERVAL 15 MINUTE) adjacent_15min,count(*) FILTER(valid) valid_15min_edges,count(*) FILTER(di<0) negative_import_edges,count(*) FILTER(de<0) negative_export_edges FROM edges) TO 'edge_counts.json' (FORMAT JSON,ARRAY true);
CREATE TABLE full_days AS SELECT id,CAST(t_start AS DATE) "day",sum(di) import_kwh,sum(de) export_kwh FROM edges WHERE valid GROUP BY id,CAST(t_start AS DATE) HAVING count(*)=96 AND min(t_start)=CAST(CAST(min(t_start) AS DATE) AS TIMESTAMP) AND max(t_start)=min(t_start)+INTERVAL '23 hours 45 minutes';
CREATE TABLE homes AS SELECT * FROM read_csv('@RAW@/w1_household_information_and_history.csv',all_varchar=true);
CREATE TABLE apps AS SELECT * FROM read_csv('@RAW@/w1_appliances.csv',all_varchar=true);
CREATE TABLE survey_dates AS SELECT household_ID,try_strptime(wave1,'%m/%d/%Y')::DATE w1 FROM read_csv('@RAW@/survey_dates.csv',all_varchar=true);
CREATE TABLE after_survey_days AS SELECT f.* FROM full_days f JOIN survey_dates s ON f.id=s.household_ID JOIN homes h ON f.id=h.household_ID WHERE f."day">s.w1 AND f.id IN (SELECT household_ID FROM apps);
CREATE TABLE runs AS WITH a AS(SELECT *,"day"-CAST(row_number() OVER(PARTITION BY id ORDER BY "day") AS INTEGER) AS grp FROM after_survey_days) SELECT id,min("day") start_day,max("day") end_day,count(*) AS days,sum(export_kwh) export_kwh FROM a GROUP BY id,grp;
CREATE TABLE qualifying AS SELECT * FROM runs WHERE days>=8;
COPY (SELECT count(*) runs,count(distinct id) households,sum(days-7) windows_7plus1 FROM qualifying) TO 'qualifying_counts.json' (FORMAT JSON,ARRAY true);
COPY (SELECT q.*,h.no_of_electricity_meters,h.type_of_house,h.no_of_household_members,h.is_there_business_carried_out_in_the_household,s.w1,(SELECT count(*) FROM apps a WHERE a.household_ID=q.id) ordinary_appliance_rows FROM qualifying q JOIN homes h ON q.id=h.household_ID JOIN survey_dates s ON q.id=s.household_ID ORDER BY id,start_day) TO 'qualifying_runs.csv' (HEADER);
COPY (SELECT count(distinct q.id) single_meter_no_business_households FROM qualifying q JOIN homes h ON q.id=h.household_ID WHERE h.no_of_electricity_meters='1' AND h.is_there_business_carried_out_in_the_household='No') TO 'single_meter_counts.json' (FORMAT JSON,ARRAY true);

CREATE TABLE generation AS SELECT * FROM read_csv('@RAW@/w1_electricity_generation_water_heating_cooking.csv',all_varchar=true);
CREATE TABLE demographics AS SELECT * FROM read_csv('@RAW@/w1_demographics.csv',all_varchar=true);
CREATE TABLE core_homes AS SELECT h.*,s.w1 FROM homes h JOIN survey_dates s ON h.household_ID=s.household_ID JOIN generation g ON h.household_ID=g.household_ID WHERE
h.no_of_electricity_meters='1' AND h.is_there_business_carried_out_in_the_household='No'
AND h.occupy_renters_boarders='I don''t occupy any of the above.'
AND try_cast(h.no_of_household_members AS INTEGER)>0 AND try_cast(h.floor_area AS DOUBLE)>0
AND h.type_of_house IS NOT NULL AND h.socio_economic_class IS NOT NULL
AND g.have_backup_generator='No' AND g.have_system_to_store_backup_energy='No'
AND g.generate_electicity_using_solar_energy='No' AND g.generate_electicity_using_bio_energy='No'
AND g.generate_electicity_using_mini_hydropower='No' AND g.generate_electicity_using_wind_power='No' AND g.generate_electicity_using_other_methods='No'
AND h.household_ID IN (SELECT household_ID FROM demographics GROUP BY household_ID HAVING count(*)=try_cast(h.no_of_household_members AS INTEGER) AND count(DISTINCT member_ID)=count(*) AND bool_and(try_cast(age AS INTEGER) BETWEEN 0 AND 110))
AND h.household_ID IN (SELECT household_ID FROM apps WHERE appliance_type IS NOT NULL GROUP BY household_ID HAVING count(DISTINCT appliance_type)>=2);
CREATE TABLE strict_days AS SELECT d.* FROM after_survey_days d JOIN core_homes h ON d.id=h.household_ID WHERE export_kwh=0;
CREATE TABLE strict_runs AS WITH a AS(SELECT *,"day"-CAST(row_number() OVER(PARTITION BY id ORDER BY "day") AS INTEGER) AS grp FROM strict_days) SELECT id,min("day") start_day,max("day") end_day,count(*) AS days FROM a GROUP BY id,grp HAVING count(*)>=8;
CREATE TABLE windows AS SELECT id,start_day+CAST(i AS INTEGER) history_start,start_day+CAST(i AS INTEGER)+7 target_day,start_day+CAST(i AS INTEGER)+8 target_end FROM strict_runs CROSS JOIN LATERAL range(days-7) r(i);
COPY (SELECT * FROM strict_runs ORDER BY id,start_day) TO 'strict_runs.csv' (HEADER);
COPY (SELECT * FROM windows ORDER BY id,history_start) TO 'windows_7plus1.csv' (HEADER);
COPY (SELECT count(*) runs,count(DISTINCT id) households,sum(days-7) windows_7plus1,min(start_day) first_day,max(end_day) last_day,min(days) minimum_run_days,max(days) maximum_run_days FROM strict_runs) TO 'strict_counts.json' (FORMAT JSON,ARRAY true);
CREATE TABLE final_homes AS SELECT * FROM core_homes WHERE household_ID IN (SELECT id FROM strict_runs);
COPY (SELECT * FROM final_homes ORDER BY household_ID) TO 'household_profiles.json' (FORMAT JSON,ARRAY true);
COPY (SELECT a.* FROM apps a JOIN final_homes h USING(household_ID) ORDER BY household_ID,appliance_ID) TO 'household_appliances.json' (FORMAT JSON,ARRAY true);
COPY (SELECT g.* FROM generation g JOIN final_homes h USING(household_ID) ORDER BY household_ID) TO 'household_generation.json' (FORMAT JSON,ARRAY true);
COPY (SELECT e.id,e.t_start,e.dt,e.prev_imp,e.imp,e.di import_kwh,e.prev_exp,e.exp,e.de export_kwh FROM edges e JOIN strict_runs q ON e.id=q.id WHERE e.t_start>=q.start_day AND e.t_start<q.end_day+INTERVAL 1 DAY AND e.valid ORDER BY e.id,e.t_start) TO 'qualified_intervals.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
CREATE TABLE sample_runs AS SELECT * FROM strict_runs QUALIFY row_number() OVER(PARTITION BY id ORDER BY start_day)=1 ORDER BY id LIMIT 10;
COPY (SELECT e.id,e.t_start,e.dt,e.prev_imp,e.imp,e.di import_kwh,e.prev_exp,e.exp,e.de export_kwh FROM edges e JOIN sample_runs q ON e.id=q.id WHERE e.t_start>=q.start_day AND e.t_start<q.start_day+INTERVAL 8 DAY AND e.valid ORDER BY e.id,e.t_start) TO 'ten_home_8day_intervals.csv' (HEADER);
COPY (SELECT * FROM final_homes WHERE household_ID IN(SELECT id FROM sample_runs) ORDER BY household_ID) TO 'ten_home_profiles.json' (FORMAT JSON,ARRAY true);

COPY (SELECT a.* FROM read_csv('@RAW@/w1_ac_roster.csv',all_varchar=true) a JOIN final_homes h USING(household_ID) ORDER BY household_ID) TO 'household_ac_roster.json' (FORMAT JSON,ARRAY true);

COPY (SELECT a.* FROM read_csv('@RAW@/w1_fan_roster.csv',all_varchar=true) a JOIN final_homes h USING(household_ID) ORDER BY household_ID) TO 'household_fan_roster.json' (FORMAT JSON,ARRAY true);

COPY (SELECT a.* FROM read_csv('@RAW@/w1_light_roster.csv',all_varchar=true) a JOIN final_homes h USING(household_ID) ORDER BY household_ID) TO 'household_light_roster.json' (FORMAT JSON,ARRAY true);

COPY (SELECT d.* FROM demographics d JOIN final_homes h USING(household_ID) ORDER BY household_ID,member_ID) TO 'household_demographics.json' (FORMAT JSON,ARRAY true);
