# mygo - 统一数据库客户端

## 版本信息
- 版本: 1.0.0  
- 构建时间: 2026-01-17

## 🆕 新功能
✅ SHOW CREATE DATABASE 支持
✅ 完善的 --help 帮助系统  
✅ 智能默认数据库连接
✅ 修复 SSL 错误提示

## 使用方法
```bash
# PostgreSQL (自动连接 postgres 数据库)
./mygo -u postgres -H 127.0.0.1 -t pg -p your_password

# MySQL (自动连接 mysql 数据库)  
./mygo -u root -H 127.0.0.1 -t mysql -p your_password
```

## 新命令
```sql
show --help;                    -- 查看所有命令
show create --help;             -- 查看 CREATE 语法
SHOW CREATE DATABASE db_name;   -- 显示数据库创建语句
```
