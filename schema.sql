-- 알뜰티켓 DB 스키마 (MariaDB) — CLAUDE.md 4절
CREATE TABLE IF NOT EXISTS inquiries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source ENUM('form','channeltalk','phone','kakao') NOT NULL DEFAULT 'form',
  name VARCHAR(40) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  category VARCHAR(40),
  amount_range VARCHAR(20),
  memo TEXT,
  status ENUM('new','consulting','done','hold') DEFAULT 'new',
  amount_final INT NULL,               -- 입금완료 시 입력한 매입금액 (랜딩 피드 노출용)
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status_created (status, created_at)
) DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(40) UNIQUE NOT NULL,
  password_hash VARCHAR(200) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;
