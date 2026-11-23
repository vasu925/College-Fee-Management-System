CREATE DATABASE IF NOT EXISTS college_fees
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'fee_admin'@'localhost'
  IDENTIFIED BY 'replace_this_with_a_strong_password';

GRANT ALL PRIVILEGES ON college_fees.* TO 'fee_admin'@'localhost';
FLUSH PRIVILEGES;

USE college_fees;
-- Application tables are created by: flask --app app init-db
