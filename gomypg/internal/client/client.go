package client

import (
	"database/sql"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/chzyer/readline"
	"github.com/olekukonko/tablewriter"

	"gomypg/internal/db"
	"gomypg/internal/translator"
)

// Config holds client configuration
type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
	DBType   string
	SSLMode  string
}

// Client represents the database client
type Client struct {
	conn           *db.Connection
	translator     *translator.Translator
	config         *Config
	expandedOutput bool
}

// New creates a new client
func New(cfg *Config) (*Client, error) {
	dbType := db.MySQL
	if cfg.DBType == "pg" || cfg.DBType == "postgresql" {
		dbType = db.PostgreSQL
	}

	dbCfg := &db.Config{
		Host:     cfg.Host,
		Port:     cfg.Port,
		User:     cfg.User,
		Password: cfg.Password,
		Database: cfg.Database,
		DBType:   dbType,
		SSLMode:  cfg.SSLMode,
	}

	conn, err := db.New(dbCfg)
	if err != nil {
		return nil, err
	}

	return &Client{
		conn:       conn,
		translator: translator.New(dbType),
		config:     cfg,
	}, nil
}

// Close closes the client
func (c *Client) Close() error {
	return c.conn.Close()
}

// Run starts the interactive client
func (c *Client) Run() error {
	dbTypeStr := "MySQL"
	if c.conn.Config.DBType == db.PostgreSQL {
		dbTypeStr = "PostgreSQL"
	}

	fmt.Printf("Welcome to mygo, the unified database client.\n")
	fmt.Printf("Connected to %s at %s:%d\n", dbTypeStr, c.config.Host, c.config.Port)
	fmt.Printf("Database: %s\n", c.config.Database)
	fmt.Printf("Type 'help' or '\\?' for help. Type 'quit' or '\\q' to exit.\n\n")

	rl, err := readline.NewEx(&readline.Config{
		Prompt:          c.getPrompt(),
		HistoryFile:     "/tmp/mygo_history",
		InterruptPrompt: "^C",
		EOFPrompt:       "exit",
	})
	if err != nil {
		return err
	}
	defer rl.Close()

	var multiLineBuffer strings.Builder
	inMultiLine := false

	for {
		if inMultiLine {
			rl.SetPrompt("    -> ")
		} else {
			rl.SetPrompt(c.getPrompt())
		}

		line, err := rl.Readline()
		if err != nil {
			if err == readline.ErrInterrupt {
				if inMultiLine {
					multiLineBuffer.Reset()
					inMultiLine = false
					fmt.Println()
					continue
				}
				continue
			}
			if err == io.EOF {
				fmt.Println("\nBye!")
				return nil
			}
			return err
		}

		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		// Check for quit commands
		lowerLine := strings.ToLower(line)
		if lowerLine == "quit" || lowerLine == "exit" || lowerLine == "\\q" || lowerLine == "\\quit" {
			fmt.Println("Bye!")
			return nil
		}

		// Check for help
		if lowerLine == "help" || lowerLine == "\\?" || lowerLine == "\\help" {
			c.printHelp()
			continue
		}

		// Handle multi-line input
		if !strings.HasSuffix(line, ";") && !strings.HasPrefix(line, "\\") {
			multiLineBuffer.WriteString(line)
			multiLineBuffer.WriteString(" ")
			inMultiLine = true
			continue
		}

		var fullQuery string
		if inMultiLine {
			multiLineBuffer.WriteString(line)
			fullQuery = multiLineBuffer.String()
			multiLineBuffer.Reset()
			inMultiLine = false
		} else {
			fullQuery = line
		}

		if err := c.executeQuery(fullQuery); err != nil {
			fmt.Fprintf(os.Stderr, "ERROR: %v\n", err)
		}
	}
}

func (c *Client) getPrompt() string {
	dbName := c.config.Database
	if dbName == "" {
		dbName = "(none)"
	}
	return fmt.Sprintf("mygo [%s]> ", dbName)
}

func (c *Client) executeQuery(query string) error {
	result, err := c.translator.Translate(query)
	if err != nil {
		return err
	}

	// Handle special commands
	if result.IsSpecial {
		return c.handleSpecialCommand(result)
	}

	// Execute the query
	rows, err := c.conn.Query(result.Query)
	if err != nil {
		return err
	}
	defer rows.Close()

	return c.printResults(rows)
}

func (c *Client) handleSpecialCommand(result *translator.TranslationResult) error {
	switch result.SpecialType {
	case "use_database":
		if len(result.Args) < 1 {
			return fmt.Errorf("database name required")
		}
		dbName := result.Args[0]
		if err := c.conn.SetDatabase(dbName); err != nil {
			return err
		}
		c.config.Database = dbName
		fmt.Printf("Database changed to '%s'\n", dbName)
		return nil

	case "quit":
		fmt.Println("Bye!")
		os.Exit(0)
		return nil

	case "help":
		c.printHelp()
		return nil

	case "toggle_expanded":
		c.expandedOutput = !c.expandedOutput
		if c.expandedOutput {
			fmt.Println("Expanded display is on.")
		} else {
			fmt.Println("Expanded display is off.")
		}
		return nil

	case "show_create_table":
		if len(result.Args) < 1 {
			return fmt.Errorf("table name required")
		}
		return c.showCreateTable(result.Args[0])

	case "show_create_database":
		if len(result.Args) < 1 {
			return fmt.Errorf("database name required")
		}
		return c.showCreateDatabase(result.Args[0])

	case "cross_db_query":
		// For cross-database queries, we need to handle specially
		// For now, just execute the query in current database
		rows, err := c.conn.Query(result.Query)
		if err != nil {
			return err
		}
		defer rows.Close()
		return c.printResults(rows)

	case "show_help":
		c.printShowHelp()
		return nil

	case "show_create_help":
		c.printShowCreateHelp()
		return nil

	case "show_tables_help":
		c.printShowTablesHelp()
		return nil

	case "show_columns_help":
		c.printShowColumnsHelp()
		return nil

	default:
		return fmt.Errorf("unknown special command: %s", result.SpecialType)
	}
}

func (c *Client) showCreateTable(tableName string) error {
	if c.conn.Config.DBType == db.MySQL {
		rows, err := c.conn.Query("SHOW CREATE TABLE " + tableName)
		if err != nil {
			return err
		}
		defer rows.Close()
		return c.printResults(rows)
	}

	// PostgreSQL: Generate CREATE TABLE statement
	query := fmt.Sprintf(`
		SELECT 
			'CREATE TABLE ' || '%s' || ' (' || E'\n' ||
			string_agg(
				'  ' || column_name || ' ' || 
				CASE 
					WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
					WHEN data_type = 'character' THEN 'CHAR(' || character_maximum_length || ')'
					WHEN data_type = 'numeric' THEN 'NUMERIC(' || numeric_precision || ',' || numeric_scale || ')'
					ELSE UPPER(data_type)
				END ||
				CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
				CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END,
				',' || E'\n'
				ORDER BY ordinal_position
			) || E'\n);' AS "Create Table"
		FROM information_schema.columns
		WHERE table_schema = 'public' AND table_name = '%s'
		GROUP BY table_name
	`, tableName, tableName)

	rows, err := c.conn.Query(query)
	if err != nil {
		return err
	}
	defer rows.Close()

	// Print table name and create statement
	fmt.Printf("Table: %s\n", tableName)
	return c.printResults(rows)
}

func (c *Client) showCreateDatabase(dbName string) error {
	if c.conn.Config.DBType == db.MySQL {
		rows, err := c.conn.Query("SHOW CREATE DATABASE " + dbName)
		if err != nil {
			return err
		}
		defer rows.Close()
		return c.printResults(rows)
	}

	// PostgreSQL: Generate CREATE DATABASE statement
	query := fmt.Sprintf(`
		SELECT 
			'CREATE DATABASE ' || datname || 
			' WITH OWNER = ' || pg_catalog.pg_get_userbyid(datdba) ||
			' ENCODING = ''' || pg_encoding_to_char(encoding) || '''' ||
			CASE 
				WHEN datcollate IS NOT NULL THEN ' LC_COLLATE = ''' || datcollate || ''''
				ELSE ''
			END ||
			CASE 
				WHEN datctype IS NOT NULL THEN ' LC_CTYPE = ''' || datctype || ''''
				ELSE ''
			END ||
			';' AS "Create Database"
		FROM pg_database 
		WHERE datname = '%s'
	`, dbName)

	rows, err := c.conn.Query(query)
	if err != nil {
		return err
	}
	defer rows.Close()

	// Print database name and create statement
	fmt.Printf("Database: %s\n", dbName)
	return c.printResults(rows)
}

func (c *Client) printResults(rows *sql.Rows) error {
	columns, err := rows.Columns()
	if err != nil {
		return err
	}

	if len(columns) == 0 {
		fmt.Println("Empty set")
		return nil
	}

	// Prepare value holders
	values := make([]interface{}, len(columns))
	valuePtrs := make([]interface{}, len(columns))
	for i := range values {
		valuePtrs[i] = &values[i]
	}

	var data [][]string
	for rows.Next() {
		if err := rows.Scan(valuePtrs...); err != nil {
			return err
		}

		row := make([]string, len(columns))
		for i, val := range values {
			if val == nil {
				row[i] = "NULL"
			} else {
				switch v := val.(type) {
				case []byte:
					row[i] = string(v)
				default:
					row[i] = fmt.Sprintf("%v", v)
				}
			}
		}
		data = append(data, row)
	}

	if err := rows.Err(); err != nil {
		return err
	}

	if len(data) == 0 {
		fmt.Println("Empty set")
		return nil
	}

	if c.expandedOutput {
		c.printExpandedResults(columns, data)
	} else {
		c.printTableResults(columns, data)
	}

	fmt.Printf("%d row(s) in set\n", len(data))
	return nil
}

func (c *Client) printTableResults(columns []string, data [][]string) {
	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader(columns)
	table.SetBorder(true)
	table.SetRowLine(false)
	table.SetCenterSeparator("|")
	table.SetColumnSeparator("|")
	table.SetRowSeparator("-")
	table.SetHeaderAlignment(tablewriter.ALIGN_LEFT)
	table.SetAlignment(tablewriter.ALIGN_LEFT)
	table.SetAutoWrapText(false)

	for _, row := range data {
		table.Append(row)
	}

	table.Render()
}

func (c *Client) printExpandedResults(columns []string, data [][]string) {
	for i, row := range data {
		fmt.Printf("*************************** %d. row ***************************\n", i+1)
		for j, col := range columns {
			fmt.Printf("%20s: %s\n", col, row[j])
		}
	}
}

func (c *Client) printHelp() {
	help := `
mygo - Unified MySQL-style Database Client
===========================================

General Commands:
  help, \?          Show this help message
  quit, exit, \q    Exit the client
  \x                Toggle expanded output mode

MySQL-style Commands (work on both MySQL and PostgreSQL):
  SHOW DATABASES;                   List all databases
  SHOW TABLES;                      List tables in current database
  SHOW TABLES FROM db;              List tables in specified database
  SHOW FULL TABLES;                 List tables with type
  SHOW COLUMNS FROM table;          Show table columns
  DESC table;                       Describe table structure
  DESCRIBE table;                   Same as DESC
  SHOW CREATE TABLE table;          Show CREATE TABLE statement
  SHOW INDEX FROM table;            Show table indexes
  SHOW PROCESSLIST;                 Show active connections
  SHOW STATUS;                      Show server status
  SHOW VARIABLES;                   Show server variables
  SHOW VARIABLES LIKE 'pattern';    Show matching variables
  SHOW GRANTS;                      Show current user grants
  SHOW GRANTS FOR user;             Show grants for user
  SHOW TABLE STATUS;                Show table status info
  SHOW TRIGGERS;                    Show triggers
  SHOW FUNCTION STATUS;             Show functions
  SHOW ENGINES;                     Show storage engines
  SHOW CHARSET;                     Show character sets
  SHOW COLLATION;                   Show collations
  USE database;                     Switch to database

PostgreSQL Backslash Commands (also supported):
  \l, \list         List databases
  \dt               List tables
  \dt+              List tables with size
  \d                List all relations
  \d table          Describe table
  \di               List indexes
  \dv               List views
  \df               List functions
  \du               List users/roles
  \dn               List schemas
  \c database       Connect to database

Standard SQL:
  SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, etc.

Note: When connected to PostgreSQL, MySQL-style commands are
automatically translated to their PostgreSQL equivalents.
`
	fmt.Println(help)
}

func (c *Client) printShowHelp() {
	help := `
SHOW Command Help
=================

Available SHOW commands:

Database and Schema:
  SHOW DATABASES;                   List all databases
  SHOW SCHEMAS;                     List all schemas

Tables and Structure:
  SHOW TABLES;                      List tables in current database
  SHOW TABLES FROM db;              List tables in specified database
  SHOW FULL TABLES;                 List tables with type
  SHOW TABLE STATUS;                Show table status info

Column and Index Information:
  SHOW COLUMNS FROM table;          Show table columns
  SHOW FULL COLUMNS FROM table;     Show detailed column info
  SHOW INDEX FROM table;            Show table indexes
  SHOW CREATE TABLE table;          Show CREATE TABLE statement

Server Information:
  SHOW STATUS;                      Show server status
  SHOW VARIABLES;                   Show server variables
  SHOW VARIABLES LIKE 'pattern';    Show matching variables
  SHOW PROCESSLIST;                 Show active connections

User and Security:
  SHOW GRANTS;                      Show current user grants
  SHOW GRANTS FOR user;             Show grants for user

Other:
  SHOW TRIGGERS;                    Show triggers
  SHOW FUNCTION STATUS;             Show functions
  SHOW ENGINES;                     Show storage engines
  SHOW CHARSET;                     Show character sets
  SHOW COLLATION;                   Show collations

Usage: 
  - Use 'SHOW <command> --help' for specific command help
  - Example: SHOW CREATE --help, SHOW TABLES --help
`
	fmt.Println(help)
}

func (c *Client) printShowCreateHelp() {
	help := `
SHOW CREATE Command Help
========================

SHOW CREATE TABLE table_name;
SHOW CREATE DATABASE database_name;

Description:
  - SHOW CREATE TABLE: Shows the CREATE TABLE statement for the specified table
  - SHOW CREATE DATABASE: Shows the CREATE DATABASE statement for the specified database
  
Examples:
  SHOW CREATE TABLE users;
  SHOW CREATE TABLE categories;
  SHOW CREATE TABLE products;
  
  SHOW CREATE DATABASE mydb;
  SHOW CREATE DATABASE t11;
  SHOW CREATE DATABASE postgres;

Note:
  - Replace 'table_name' with the actual name of your table
  - Replace 'database_name' with the actual name of your database
  - The table/database must exist
  - For PostgreSQL, this generates equivalent CREATE statements
`
	fmt.Println(help)
}

func (c *Client) printShowTablesHelp() {
	help := `
SHOW TABLES Command Help
========================

SHOW TABLES;                      List tables in current database
SHOW TABLES FROM database_name;   List tables in specified database
SHOW FULL TABLES;                 List tables with type information

Examples:
  SHOW TABLES;
  SHOW TABLES FROM mydb;
  SHOW FULL TABLES;

Description:
  - SHOW TABLES: Lists all tables in the current database
  - SHOW TABLES FROM db: Lists tables in the specified database
  - SHOW FULL TABLES: Shows tables with additional type information
`
	fmt.Println(help)
}

func (c *Client) printShowColumnsHelp() {
	help := `
SHOW COLUMNS Command Help
=========================

SHOW COLUMNS FROM table_name;
SHOW FULL COLUMNS FROM table_name;
DESC table_name;
DESCRIBE table_name;

Examples:
  SHOW COLUMNS FROM users;
  SHOW FULL COLUMNS FROM products;
  DESC categories;
  DESCRIBE orders;

Description:
  - SHOW COLUMNS FROM: Shows basic column information (name, type, null, key, default, extra)
  - SHOW FULL COLUMNS FROM: Shows detailed column information including collation and privileges
  - DESC/DESCRIBE: Shorthand for SHOW COLUMNS FROM

Note:
  - Replace 'table_name' with the actual name of your table
  - The table must exist in the current database
`
	fmt.Println(help)
}
