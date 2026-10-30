-- 맥스페이 DB 스키마 (MariaDB) — CLAUDE.md 4절
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

-- 블로그 글 (어드민 /admin/posts). status='published' AND published_at <= 현재(KST) 인 글만 공개
CREATE TABLE IF NOT EXISTS posts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(190) NOT NULL,
  title VARCHAR(200) NOT NULL,
  summary VARCHAR(500) NULL,
  body MEDIUMTEXT NOT NULL,                -- 마크다운 원문 (mdlite.py 로 렌더)
  cover_image VARCHAR(255) NULL,
  status ENUM('draft','published') NOT NULL DEFAULT 'draft',
  published_at DATETIME NULL,              -- KST 기준
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_slug (slug),
  INDEX idx_status_pub (status, published_at)
) DEFAULT CHARSET=utf8mb4;
