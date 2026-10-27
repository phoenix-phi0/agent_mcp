SELECT st.id FROM teacher_rules_relay_state st JOIN teacher_rules_relay r ON r.id = st.relay_id WHERE st.id = CAST(:id AS INTEGER) AND (r.subject_id = CAST(:subj AS INTEGER) OR r.subject_id = 0)
