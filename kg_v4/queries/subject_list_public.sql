SELECT i.id AS id, i.code AS code, i.name AS name, i.kind AS kind, i.visibility AS visibility FROM subject_info i WHERE i.visibility = 'public' AND i.status = 'active' ORDER BY i.id
