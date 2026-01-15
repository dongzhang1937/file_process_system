-- PostgreSQL 测试数据库初始化脚本
-- 包含：表、视图、索引、函数、存储过程、触发器、序列、类型等

-- ============================================
-- 1. 创建测试数据库（如果需要）
-- ============================================
-- CREATE DATABASE testdb;
-- \c testdb

-- ============================================
-- 2. 创建自定义类型
-- ============================================
DROP TYPE IF EXISTS user_status CASCADE;
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'pending', 'banned');

DROP TYPE IF EXISTS address_type CASCADE;
CREATE TYPE address_type AS (
    street VARCHAR(200),
    city VARCHAR(100),
    country VARCHAR(100),
    zip_code VARCHAR(20)
);

-- ============================================
-- 3. 创建序列
-- ============================================
DROP SEQUENCE IF EXISTS order_seq CASCADE;
CREATE SEQUENCE order_seq
    START WITH 1000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- ============================================
-- 4. 创建表
-- ============================================

-- 用户表
DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    status user_status DEFAULT 'pending',
    profile JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS '用户信息表';
COMMENT ON COLUMN users.id IS '用户ID';
COMMENT ON COLUMN users.username IS '用户名';
COMMENT ON COLUMN users.status IS '用户状态';

-- 部门表
DROP TABLE IF EXISTS departments CASCADE;
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INTEGER REFERENCES departments(id),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 员工表
DROP TABLE IF EXISTS employees CASCADE;
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id),
    employee_no VARCHAR(20) UNIQUE,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    hire_date DATE NOT NULL,
    salary NUMERIC(12, 2),
    address address_type,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 产品分类表
DROP TABLE IF EXISTS categories CASCADE;
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    level INTEGER DEFAULT 1,
    path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 产品表
DROP TABLE IF EXISTS products CASCADE;
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category_id INTEGER REFERENCES categories(id),
    price NUMERIC(10, 2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    attributes JSONB,
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 订单表
DROP TABLE IF EXISTS orders CASCADE;
CREATE TABLE orders (
    id BIGINT PRIMARY KEY DEFAULT nextval('order_seq'),
    user_id INTEGER REFERENCES users(id),
    order_no VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'pending',
    total_amount NUMERIC(12, 2) NOT NULL,
    shipping_address JSONB,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 订单明细表
DROP TABLE IF EXISTS order_items CASCADE;
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    subtotal NUMERIC(12, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED
);

-- 日志表（用于分区演示）
DROP TABLE IF EXISTS logs CASCADE;
CREATE TABLE logs (
    id SERIAL,
    log_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(10),
    message TEXT,
    metadata JSONB
) PARTITION BY RANGE (log_time);

-- 创建分区
CREATE TABLE logs_2026_01 PARTITION OF logs
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE logs_2026_02 PARTITION OF logs
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- ============================================
-- 5. 创建索引
-- ============================================
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_profile ON users USING GIN(profile);

CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_price ON products(price);
CREATE INDEX idx_products_attrs ON products USING GIN(attributes);

CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);

CREATE UNIQUE INDEX idx_employees_user ON employees(user_id);

-- ============================================
-- 6. 创建视图
-- ============================================

-- 简单视图：活跃用户
CREATE OR REPLACE VIEW v_active_users AS
SELECT id, username, email, created_at
FROM users
WHERE status = 'active';

-- 复杂视图：订单统计
CREATE OR REPLACE VIEW v_order_summary AS
SELECT 
    u.id AS user_id,
    u.username,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_spent,
    MAX(o.created_at) AS last_order_date
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username;

-- 物化视图：产品销售统计
DROP MATERIALIZED VIEW IF EXISTS mv_product_sales;
CREATE MATERIALIZED VIEW mv_product_sales AS
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.sku,
    COUNT(oi.id) AS times_sold,
    COALESCE(SUM(oi.quantity), 0) AS total_quantity,
    COALESCE(SUM(oi.subtotal), 0) AS total_revenue
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
GROUP BY p.id, p.name, p.sku;

CREATE UNIQUE INDEX idx_mv_product_sales ON mv_product_sales(product_id);

-- ============================================
-- 7. 创建函数
-- ============================================

-- 标量函数：计算折扣价格
CREATE OR REPLACE FUNCTION calc_discount_price(
    original_price NUMERIC,
    discount_percent NUMERIC
) RETURNS NUMERIC AS $$
BEGIN
    RETURN ROUND(original_price * (1 - discount_percent / 100), 2);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 表函数：获取用户订单
CREATE OR REPLACE FUNCTION get_user_orders(p_user_id INTEGER)
RETURNS TABLE (
    order_id BIGINT,
    order_no VARCHAR,
    total_amount NUMERIC,
    status VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT o.id, o.order_no, o.total_amount, o.status, o.created_at
    FROM orders o
    WHERE o.user_id = p_user_id
    ORDER BY o.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- 聚合函数辅助：计算订单总额
CREATE OR REPLACE FUNCTION calculate_order_total(p_order_id BIGINT)
RETURNS NUMERIC AS $$
DECLARE
    v_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(quantity * unit_price), 0)
    INTO v_total
    FROM order_items
    WHERE order_id = p_order_id;
    
    RETURN v_total;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 8. 创建存储过程 (PostgreSQL 11+)
-- ============================================

-- 存储过程：创建订单
CREATE OR REPLACE PROCEDURE create_order(
    p_user_id INTEGER,
    p_items JSONB,  -- [{"product_id": 1, "quantity": 2}, ...]
    OUT p_order_id BIGINT
)
LANGUAGE plpgsql AS $$
DECLARE
    v_order_no VARCHAR;
    v_item JSONB;
    v_product_id INTEGER;
    v_quantity INTEGER;
    v_price NUMERIC;
    v_total NUMERIC := 0;
BEGIN
    -- 生成订单号
    v_order_no := 'ORD' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDDHH24MISS') || LPAD(nextval('order_seq')::TEXT, 6, '0');
    
    -- 创建订单
    INSERT INTO orders (user_id, order_no, total_amount)
    VALUES (p_user_id, v_order_no, 0)
    RETURNING id INTO p_order_id;
    
    -- 添加订单项
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_product_id := (v_item->>'product_id')::INTEGER;
        v_quantity := (v_item->>'quantity')::INTEGER;
        
        SELECT price INTO v_price FROM products WHERE id = v_product_id;
        
        INSERT INTO order_items (order_id, product_id, quantity, unit_price)
        VALUES (p_order_id, v_product_id, v_quantity, v_price);
        
        v_total := v_total + (v_quantity * v_price);
    END LOOP;
    
    -- 更新订单总额
    UPDATE orders SET total_amount = v_total WHERE id = p_order_id;
    
    COMMIT;
END;
$$;

-- 存储过程：更新用户状态
CREATE OR REPLACE PROCEDURE update_user_status(
    p_user_id INTEGER,
    p_new_status user_status
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE users 
    SET status = p_new_status, updated_at = CURRENT_TIMESTAMP
    WHERE id = p_user_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User % not found', p_user_id;
    END IF;
    
    COMMIT;
END;
$$;

-- ============================================
-- 9. 创建触发器
-- ============================================

-- 触发器函数：更新 updated_at
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为 users 表创建触发器
DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- 为 products 表创建触发器
DROP TRIGGER IF EXISTS trg_products_updated ON products;
CREATE TRIGGER trg_products_updated
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- 触发器函数：记录订单变更日志
CREATE OR REPLACE FUNCTION log_order_changes()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO logs (level, message, metadata)
    VALUES (
        'INFO',
        'Order status changed',
        jsonb_build_object(
            'order_id', NEW.id,
            'old_status', OLD.status,
            'new_status', NEW.status,
            'changed_at', CURRENT_TIMESTAMP
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_order_status_log ON orders;
CREATE TRIGGER trg_order_status_log
    AFTER UPDATE OF status ON orders
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION log_order_changes();

-- ============================================
-- 10. 插入测试数据
-- ============================================

-- 插入用户
INSERT INTO users (username, email, password_hash, status, profile) VALUES
('admin', 'admin@example.com', 'hash_admin_123', 'active', '{"role": "admin", "permissions": ["all"]}'),
('john_doe', 'john@example.com', 'hash_john_456', 'active', '{"role": "user", "preferences": {"theme": "dark"}}'),
('jane_smith', 'jane@example.com', 'hash_jane_789', 'active', '{"role": "user", "preferences": {"theme": "light"}}'),
('bob_wilson', 'bob@example.com', 'hash_bob_000', 'pending', NULL),
('alice_brown', 'alice@example.com', 'hash_alice_111', 'inactive', '{"role": "user"}');

-- 插入部门
INSERT INTO departments (name, parent_id, description) VALUES
('总公司', NULL, '公司总部'),
('技术部', 1, '负责技术研发'),
('销售部', 1, '负责产品销售'),
('人事部', 1, '负责人力资源'),
('后端组', 2, '后端开发团队'),
('前端组', 2, '前端开发团队');

-- 插入员工
INSERT INTO employees (user_id, department_id, employee_no, first_name, last_name, hire_date, salary) VALUES
(1, 2, 'EMP001', 'Admin', 'User', '2020-01-01', 50000.00),
(2, 5, 'EMP002', 'John', 'Doe', '2021-03-15', 35000.00),
(3, 6, 'EMP003', 'Jane', 'Smith', '2021-06-01', 38000.00);

-- 插入产品分类
INSERT INTO categories (name, parent_id, level, path) VALUES
('电子产品', NULL, 1, '/电子产品'),
('服装', NULL, 1, '/服装'),
('手机', 1, 2, '/电子产品/手机'),
('电脑', 1, 2, '/电子产品/电脑'),
('男装', 2, 2, '/服装/男装'),
('女装', 2, 2, '/服装/女装');

-- 插入产品
INSERT INTO products (sku, name, description, category_id, price, stock_quantity, attributes) VALUES
('PHONE-001', 'iPhone 15 Pro', '苹果最新旗舰手机', 3, 8999.00, 100, '{"color": "黑色", "storage": "256GB"}'),
('PHONE-002', 'Samsung Galaxy S24', '三星旗舰手机', 3, 6999.00, 150, '{"color": "白色", "storage": "128GB"}'),
('LAPTOP-001', 'MacBook Pro 14', '苹果笔记本电脑', 4, 14999.00, 50, '{"chip": "M3 Pro", "ram": "18GB"}'),
('LAPTOP-002', 'ThinkPad X1 Carbon', '联想商务笔记本', 4, 9999.00, 80, '{"cpu": "i7-1365U", "ram": "16GB"}'),
('SHIRT-001', '商务衬衫', '男士商务衬衫', 5, 299.00, 500, '{"size": ["S", "M", "L", "XL"], "color": "白色"}'),
('DRESS-001', '连衣裙', '女士夏季连衣裙', 6, 399.00, 300, '{"size": ["S", "M", "L"], "color": "红色"}');

-- 插入订单
INSERT INTO orders (user_id, order_no, status, total_amount, shipping_address) VALUES
(2, 'ORD20260101001', 'completed', 8999.00, '{"city": "北京", "address": "朝阳区xxx"}'),
(2, 'ORD20260102002', 'shipped', 15298.00, '{"city": "北京", "address": "朝阳区xxx"}'),
(3, 'ORD20260103003', 'pending', 6999.00, '{"city": "上海", "address": "浦东新区xxx"}');

-- 插入订单明细
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1000, 1, 1, 8999.00),
(1001, 1, 1, 8999.00),
(1001, 5, 2, 299.00),
(1001, 6, 1, 399.00),
(1002, 2, 1, 6999.00);

-- 插入日志
INSERT INTO logs (log_time, level, message, metadata) VALUES
('2026-01-05 10:00:00', 'INFO', 'System started', '{"version": "1.0.0"}'),
('2026-01-05 10:01:00', 'INFO', 'User logged in', '{"user_id": 1}'),
('2026-01-05 10:02:00', 'WARN', 'High memory usage', '{"usage": "85%"}');

-- 刷新物化视图
REFRESH MATERIALIZED VIEW mv_product_sales;

-- ============================================
-- 11. 创建规则 (Rules)
-- ============================================
CREATE OR REPLACE RULE protect_admin AS
    ON DELETE TO users
    WHERE OLD.username = 'admin'
    DO INSTEAD NOTHING;

-- ============================================
-- 完成
-- ============================================
SELECT 'PostgreSQL test database initialized successfully!' AS message;
