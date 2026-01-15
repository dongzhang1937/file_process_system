package db

import (
	"database/sql"
	"fmt"

	_ "github.com/go-sql-driver/mysql"
	_ "github.com/lib/pq"
)

// DBType represents the database type
type DBType string

const (
	MySQL      DBType = "mysql"
	PostgreSQL DBType = "pg"
)

// Config holds database connection configuration
type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
	DBType   DBType
	SSLMode  string
}

// Connection wraps a database connection
type Connection struct {
	DB     *sql.DB
	Config *Config
}

// New creates a new database connection
func New(cfg *Config) (*Connection, error) {
	var dsn string
	var driver string

	switch cfg.DBType {
	case MySQL:
		driver = "mysql"
		dsn = fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?charset=utf8mb4&parseTime=True",
			cfg.User, cfg.Password, cfg.Host, cfg.Port, cfg.Database)
	case PostgreSQL:
		driver = "postgres"
		sslMode := cfg.SSLMode
		if sslMode == "" {
			sslMode = "disable"
		}
		
		// 构建连接字符串
		// 不指定 host 时使用 Unix socket (peer 认证)
		if cfg.Host == "" {
			// 使用 Unix socket，指定常见的 socket 目录
			socketDir := "/var/run/postgresql"
			if cfg.Password == "" {
				dsn = fmt.Sprintf("host=%s user=%s dbname=%s sslmode=%s",
					socketDir, cfg.User, cfg.Database, sslMode)
			} else {
				dsn = fmt.Sprintf("host=%s user=%s password=%s dbname=%s sslmode=%s",
					socketDir, cfg.User, cfg.Password, cfg.Database, sslMode)
			}
		} else {
			// TCP 连接
			if cfg.Password == "" {
				dsn = fmt.Sprintf("host=%s port=%d user=%s dbname=%s sslmode=%s",
					cfg.Host, cfg.Port, cfg.User, cfg.Database, sslMode)
			} else {
				dsn = fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
					cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.Database, sslMode)
			}
		}
	default:
		return nil, fmt.Errorf("unsupported database type: %s", cfg.DBType)
	}

	// Debug: print connection info (without password)
	if cfg.DBType == PostgreSQL {
		fmt.Printf("Connecting to PostgreSQL: host=%s port=%d user=%s dbname=%s sslmode=%s\n",
			cfg.Host, cfg.Port, cfg.User, cfg.Database, cfg.SSLMode)
	}

	db, err := sql.Open(driver, dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	return &Connection{
		DB:     db,
		Config: cfg,
	}, nil
}

// Close closes the database connection
func (c *Connection) Close() error {
	return c.DB.Close()
}

// Query executes a query and returns the results
func (c *Connection) Query(query string, args ...interface{}) (*sql.Rows, error) {
	return c.DB.Query(query, args...)
}

// Exec executes a statement
func (c *Connection) Exec(query string, args ...interface{}) (sql.Result, error) {
	return c.DB.Exec(query, args...)
}

// GetCurrentDatabase returns the current database name
func (c *Connection) GetCurrentDatabase() string {
	return c.Config.Database
}

// SetDatabase changes the current database
func (c *Connection) SetDatabase(dbName string) error {
	c.Config.Database = dbName
	
	// Reconnect with new database
	c.DB.Close()
	
	newConn, err := New(c.Config)
	if err != nil {
		return err
	}
	
	c.DB = newConn.DB
	return nil
}
