-- Security/performance hardening applied to the connected Supabase project.
-- Removes duplicate permissive policies, uses server-side profile roles, caches
-- auth helper calls, and indexes policy foreign keys.

DROP POLICY IF EXISTS alerts_authenticated_select ON public.alerts;
DROP POLICY IF EXISTS feedback_insert_authenticated ON public.model_feedback;
DROP POLICY IF EXISTS report_media_reporter_insert ON public.report_media;
DROP POLICY IF EXISTS report_media_owner_or_authority_select ON public.report_media;
DROP POLICY IF EXISTS reports_authenticated_insert ON public.reports;
DROP POLICY IF EXISTS reports_insert_self ON public.reports;
DROP POLICY IF EXISTS reports_select_owner_or_authority ON public.reports;
DROP POLICY IF EXISTS reports_update_authority ON public.reports;
DROP POLICY IF EXISTS tasks_authority_all ON public.response_tasks;
DROP POLICY IF EXISTS predictions_authenticated_select ON public.risk_predictions;

ALTER POLICY alerts_authority_write ON public.alerts USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY','FIELD_OFFICER')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY','FIELD_OFFICER'));
ALTER POLICY feedback_read_authority ON public.model_feedback USING ((SELECT public.is_authority()));
ALTER POLICY feedback_authenticated_insert ON public.model_feedback WITH CHECK ((SELECT auth.uid()) = created_by);
ALTER POLICY notifications_authority_insert ON public.notifications WITH CHECK ((SELECT public.is_authority()));
ALTER POLICY notifications_self_select ON public.notifications USING ((SELECT auth.uid()) = user_id OR (SELECT public.is_authority()));
ALTER POLICY notifications_self_update ON public.notifications USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
ALTER POLICY profiles_self_select ON public.profiles USING ((SELECT auth.uid()) = id OR (SELECT public.is_authority()));
ALTER POLICY profiles_self_update ON public.profiles USING ((SELECT auth.uid()) = id) WITH CHECK ((SELECT auth.uid()) = id);
ALTER POLICY report_media_owner_or_authority ON public.report_media USING (EXISTS (SELECT 1 FROM public.reports r WHERE r.id = report_media.report_id AND (r.reporter_id = (SELECT auth.uid()) OR (SELECT public.is_authority())))) WITH CHECK (EXISTS (SELECT 1 FROM public.reports r WHERE r.id = report_media.report_id AND (r.reporter_id = (SELECT auth.uid()) OR (SELECT public.is_authority()))));
ALTER POLICY reports_owner_or_authority_select ON public.reports USING ((SELECT auth.uid()) = reporter_id OR (SELECT public.is_authority()));
ALTER POLICY response_tasks_authority_write ON public.response_tasks USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY'));
ALTER POLICY response_tasks_assignee_update ON public.response_tasks USING ((SELECT auth.uid()) = assigned_to) WITH CHECK ((SELECT auth.uid()) = assigned_to);
ALTER POLICY predictions_authority_write ON public.risk_predictions USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY','FIELD_OFFICER')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY','FIELD_OFFICER'));
ALTER POLICY roads_authority_write ON public.roads USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY'));
ALTER POLICY sensor_readings_field_insert ON public.sensor_readings WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY','FIELD_OFFICER'));
ALTER POLICY sensors_authority_write ON public.sensors USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY'));
ALTER POLICY zones_authority_write ON public.zones USING ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY')) WITH CHECK ((SELECT public.current_user_role()) IN ('ADMIN','AUTHORITY'));

ALTER POLICY report_media_storage_delete ON storage.objects USING (bucket_id = 'report-media' AND ((SELECT public.is_authority()) OR (storage.foldername(name))[1] = (SELECT auth.uid())::text));
ALTER POLICY report_media_storage_insert ON storage.objects WITH CHECK (bucket_id = 'report-media' AND ((SELECT public.is_authority()) OR (storage.foldername(name))[1] = (SELECT auth.uid())::text));
ALTER POLICY report_media_storage_select ON storage.objects USING (bucket_id = 'report-media' AND ((SELECT public.is_authority()) OR (storage.foldername(name))[1] = (SELECT auth.uid())::text));
ALTER POLICY report_media_storage_update ON storage.objects USING (bucket_id = 'report-media' AND ((SELECT public.is_authority()) OR (storage.foldername(name))[1] = (SELECT auth.uid())::text)) WITH CHECK (bucket_id = 'report-media' AND ((SELECT public.is_authority()) OR (storage.foldername(name))[1] = (SELECT auth.uid())::text));

CREATE INDEX IF NOT EXISTS alerts_created_by_idx ON public.alerts(created_by);
CREATE INDEX IF NOT EXISTS model_feedback_created_by_idx ON public.model_feedback(created_by);
CREATE INDEX IF NOT EXISTS model_feedback_prediction_id_idx ON public.model_feedback(prediction_id);
CREATE INDEX IF NOT EXISTS model_feedback_zone_id_idx ON public.model_feedback(zone_id);
CREATE INDEX IF NOT EXISTS notifications_alert_id_idx ON public.notifications(alert_id);
CREATE INDEX IF NOT EXISTS report_media_report_id_idx ON public.report_media(report_id);
CREATE INDEX IF NOT EXISTS reports_reporter_id_idx ON public.reports(reporter_id);
CREATE INDEX IF NOT EXISTS response_tasks_created_by_idx ON public.response_tasks(created_by);
CREATE INDEX IF NOT EXISTS response_tasks_zone_id_idx ON public.response_tasks(zone_id);
CREATE INDEX IF NOT EXISTS satellite_data_zone_id_idx ON public.satellite_data(zone_id);
CREATE INDEX IF NOT EXISTS sensors_zone_id_idx ON public.sensors(zone_id);
CREATE INDEX IF NOT EXISTS user_devices_user_id_idx ON public.user_devices(user_id);
ALTER POLICY devices_self_all ON public.user_devices USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
