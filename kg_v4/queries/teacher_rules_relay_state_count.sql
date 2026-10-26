SELECT count(*) FROM teacher_rules_relay_state st JOIN teacher_rules_relay r ON r.id = st.relay_id WHERE (:student = '' OR st.student = :student)
