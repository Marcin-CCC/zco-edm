-- Create default folders
INSERT INTO folders (name, path, created_by) VALUES
    ('/dokumenty-medyczne', '/dokumenty-medyczne', 1),
    ('/raporty-biurowe', '/raporty-biurowe', 1),
    ('/raporty-otrieczone', '/raporty-otrieczone', 1)
ON CONFLICT (path) DO NOTHING;