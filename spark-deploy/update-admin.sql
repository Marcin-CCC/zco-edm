-- Reset admin password to bcrypt format
UPDATE users
SET hashed_password = '$2b$12$Eb4DfRLrZjU4MKdIynl5ZO/mQSky09wGg/M3aYQRln/UrHgQtpSjm'
WHERE email = 'admin@zco.szczecin.pl';