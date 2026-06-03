#!/bin/bash
# Update admin password in database
cd /home/marcin/zco-edm-app
docker exec -i edm-zco-postgres psql -U postgres -d edmdatabase -c "UPDATE users SET hashed_password = '\$2b\$12\$Eb4DfRLrZjU4MKdIynl5ZO/mQSky09wGg/M3aYQRln/UrHgQtpSjm' WHERE email = 'admin@zco.szczecin.pl';"
echo "Password updated"