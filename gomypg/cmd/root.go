package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"gomypg/internal/client"
)

var (
	host     string
	port     int
	user     string
	password string
	database string
	dbType   string
	sslMode  string
)

var rootCmd = &cobra.Command{
	Use:   "mygo",
	Short: "A unified MySQL-style client for MySQL and PostgreSQL",
	Long: `mygo is a command-line client that provides a unified MySQL-style interface
for both MySQL and PostgreSQL databases. 

When connected to PostgreSQL, you can use familiar MySQL commands like:
  SHOW DATABASES;
  SHOW TABLES;
  SHOW COLUMNS FROM table_name;
  DESC table_name;
  
These commands will be automatically translated to their PostgreSQL equivalents.`,
	Run: func(cmd *cobra.Command, args []string) {
		// 只有 MySQL 才默认 localhost，PostgreSQL 不指定 host 时使用 Unix socket
		if host == "" && dbType == "mysql" {
			host = "localhost"
		}
		if port == 0 {
			if dbType == "mysql" {
				port = 3306
			} else {
				port = 5432
			}
		}
		if user == "" {
			user = "root"
			if dbType == "pg" || dbType == "postgresql" {
				user = "postgres"
			}
		}
		
		// 为 PostgreSQL 设置默认数据库名称
		if database == "" {
			if dbType == "pg" || dbType == "postgresql" {
				database = "postgres"  // PostgreSQL 默认数据库
			} else if dbType == "mysql" {
				database = "mysql"     // MySQL 默认数据库
			}
		}

		cfg := &client.Config{
			Host:     host,
			Port:     port,
			User:     user,
			Password: password,
			Database: database,
			DBType:   dbType,
			SSLMode:  sslMode,
		}

		c, err := client.New(cfg)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		defer c.Close()

		if err := c.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
	},
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.Flags().StringVarP(&host, "host", "H", "", "Database server host (empty for PostgreSQL Unix socket)")
	rootCmd.Flags().IntVarP(&port, "port", "P", 0, "Database server port (default: 3306 for MySQL, 5432 for PostgreSQL)")
	rootCmd.Flags().StringVarP(&user, "user", "u", "", "Database user")
	rootCmd.Flags().StringVarP(&password, "password", "p", "", "Database password")
	rootCmd.Flags().StringVarP(&database, "database", "d", "", "Database name")
	rootCmd.Flags().StringVarP(&dbType, "type", "t", "mysql", "Database type: mysql or pg/postgresql")
	rootCmd.Flags().StringVar(&sslMode, "sslmode", "disable", "PostgreSQL SSL mode: disable, require, verify-ca, verify-full")

	rootCmd.MarkFlagRequired("type")
}
