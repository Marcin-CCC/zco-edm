-- Update password hashes for all users
UPDATE users 
SET hashed_password='$2b$12$TWhXAk4GGMZ8rrRWPp0OSulm1lgOxsAohuo.U1oDOuCvu3vH9OXV2' 
WHERE email='admin@zco.szczecin.pl';

UPDATE users 
SET hashed_password='$2b$12$jzuawOs5B/bsWqjVA5OfI.jryeRnYv4f.YalCzSYO20kVS3VYZqE' 
WHERE email='user1@zco.szczecin.pl';

UPDATE users 
SET hashed_password='$2b$12$bM4p1c.kxUo.eOA213mSB.feno2Z6pwYGoBp6z9RAF2Ylrk2HNTBC' 
WHERE email='user2@zco.szczecin.pl';