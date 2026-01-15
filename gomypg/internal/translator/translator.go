package translator

import (
	"fmt"
	"regexp"
	"strings"

	"gomypg/internal/db"
)

// Translator translates MySQL commands to PostgreSQL equivalents
type Translator struct {
	dbType db.DBType
}

// New creates a new translator
func New(dbType db.DBType) *Translator {
	return &Translator{dbType: dbType}
}

// TranslationResult holds the translated query and metadata
type TranslationResult struct {
	Query       string
	IsSpecial   bool   // Special command that needs custom handling
	SpecialType string // Type of special command
	Args        []string
}

// Translate converts MySQL-style commands to the appropriate database dialect
func (t *Translator) Translate(input string) (*TranslationResult, error) {
	input = strings.TrimSpace(input)
	
	// If MySQL, no translation needed for most commands
	if t.dbType == db.MySQL {
		return &TranslationResult{Query: input}, nil
	}

	// PostgreSQL translation
	return t.translateForPostgres(input)
}

func (t *Translator) translateForPostgres(input string) (*TranslationResult, error) {
	// Remove trailing semicolon for pattern matching
	trimmedInput := strings.TrimSuffix(input, ";")
	upperTrimmed := strings.ToUpper(trimmedInput)

	// SHOW DATABASES -> SELECT datname FROM pg_database
	if upperTrimmed == "SHOW DATABASES" {
		return &TranslationResult{
			Query: "SELECT datname AS \"Database\" FROM pg_database WHERE datistemplate = false ORDER BY datname",
		}, nil
	}

	// SHOW TABLES -> \dt equivalent
	if upperTrimmed == "SHOW TABLES" {
		return &TranslationResult{
			Query: `SELECT tablename AS "Tables_in_database" 
					FROM pg_tables 
					WHERE schemaname = 'public' 
					ORDER BY tablename`,
		}, nil
	}

	// SHOW FULL TABLES
	if upperTrimmed == "SHOW FULL TABLES" {
		return &TranslationResult{
			Query: `SELECT tablename AS "Tables_in_database", 
					'BASE TABLE' AS "Table_type"
					FROM pg_tables 
					WHERE schemaname = 'public' 
					ORDER BY tablename`,
		}, nil
	}

	// SHOW TABLES FROM/IN database
	showTablesFromRe := regexp.MustCompile(`(?i)^SHOW\s+TABLES\s+(FROM|IN)\s+(\w+)$`)
	if matches := showTablesFromRe.FindStringSubmatch(trimmedInput); matches != nil {
		dbName := matches[2]
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT tablename AS "Tables_in_%s" 
					FROM pg_tables 
					WHERE schemaname = 'public' 
					ORDER BY tablename`, dbName),
			IsSpecial:   true,
			SpecialType: "cross_db_query",
			Args:        []string{dbName},
		}, nil
	}

	// SHOW COLUMNS FROM table / DESC table / DESCRIBE table
	showColumnsRe := regexp.MustCompile(`(?i)^(SHOW\s+COLUMNS\s+FROM|DESC|DESCRIBE)\s+(\w+)$`)
	if matches := showColumnsRe.FindStringSubmatch(trimmedInput); matches != nil {
		tableName := matches[2]
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT 
				column_name AS "Field",
				data_type AS "Type",
				CASE WHEN is_nullable = 'YES' THEN 'YES' ELSE 'NO' END AS "Null",
				CASE 
					WHEN column_default LIKE 'nextval%%' THEN 'PRI'
					ELSE ''
				END AS "Key",
				column_default AS "Default",
				CASE 
					WHEN column_default LIKE 'nextval%%' THEN 'auto_increment'
					ELSE ''
				END AS "Extra"
			FROM information_schema.columns 
			WHERE table_schema = 'public' AND table_name = '%s'
			ORDER BY ordinal_position`, tableName),
		}, nil
	}

	// SHOW FULL COLUMNS FROM table
	showFullColumnsRe := regexp.MustCompile(`(?i)^SHOW\s+FULL\s+COLUMNS\s+FROM\s+(\w+)$`)
	if matches := showFullColumnsRe.FindStringSubmatch(trimmedInput); matches != nil {
		tableName := matches[1]
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT 
				column_name AS "Field",
				data_type AS "Type",
				character_set_name AS "Collation",
				CASE WHEN is_nullable = 'YES' THEN 'YES' ELSE 'NO' END AS "Null",
				'' AS "Key",
				column_default AS "Default",
				'' AS "Extra",
				'select,insert,update,references' AS "Privileges",
				'' AS "Comment"
			FROM information_schema.columns 
			WHERE table_schema = 'public' AND table_name = '%s'
			ORDER BY ordinal_position`, tableName),
		}, nil
	}

	// SHOW CREATE TABLE table
	showCreateTableRe := regexp.MustCompile(`(?i)^SHOW\s+CREATE\s+TABLE\s+(\w+)$`)
	if matches := showCreateTableRe.FindStringSubmatch(trimmedInput); matches != nil {
		tableName := matches[1]
		return &TranslationResult{
			IsSpecial:   true,
			SpecialType: "show_create_table",
			Args:        []string{tableName},
		}, nil
	}

	// SHOW INDEX FROM table / SHOW INDEXES FROM table / SHOW KEYS FROM table
	showIndexRe := regexp.MustCompile(`(?i)^SHOW\s+(INDEX|INDEXES|KEYS)\s+FROM\s+(\w+)$`)
	if matches := showIndexRe.FindStringSubmatch(trimmedInput); matches != nil {
		tableName := matches[2]
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT 
				schemaname AS "Table",
				indexname AS "Key_name",
				indexdef AS "Index_definition"
			FROM pg_indexes 
			WHERE schemaname = 'public' AND tablename = '%s'`, tableName),
		}, nil
	}

	// SHOW STATUS
	if upperTrimmed == "SHOW STATUS" {
		return &TranslationResult{
			Query: `SELECT name AS "Variable_name", setting AS "Value" 
					FROM pg_settings 
					ORDER BY name 
					LIMIT 50`,
		}, nil
	}

	// SHOW VARIABLES / SHOW GLOBAL VARIABLES
	if upperTrimmed == "SHOW VARIABLES" || upperTrimmed == "SHOW GLOBAL VARIABLES" {
		return &TranslationResult{
			Query: `SELECT name AS "Variable_name", setting AS "Value" 
					FROM pg_settings 
					ORDER BY name`,
		}, nil
	}

	// SHOW VARIABLES LIKE 'pattern'
	showVarsLikeRe := regexp.MustCompile(`(?i)^SHOW\s+(GLOBAL\s+)?VARIABLES\s+LIKE\s+'([^']+)'$`)
	if matches := showVarsLikeRe.FindStringSubmatch(trimmedInput); matches != nil {
		pattern := strings.ReplaceAll(matches[2], "%", "%%")
		pattern = strings.ReplaceAll(pattern, "_", ".")
		pattern = strings.ReplaceAll(pattern, "%%", ".*")
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT name AS "Variable_name", setting AS "Value" 
					FROM pg_settings 
					WHERE name ~ '%s'
					ORDER BY name`, pattern),
		}, nil
	}

	// SHOW PROCESSLIST
	if upperTrimmed == "SHOW PROCESSLIST" || upperTrimmed == "SHOW FULL PROCESSLIST" {
		return &TranslationResult{
			Query: `SELECT 
				pid AS "Id",
				usename AS "User",
				client_addr AS "Host",
				datname AS "db",
				state AS "Command",
				EXTRACT(EPOCH FROM (now() - query_start))::int AS "Time",
				state AS "State",
				query AS "Info"
			FROM pg_stat_activity 
			WHERE pid <> pg_backend_pid()`,
		}, nil
	}

	// SHOW GRANTS
	if upperTrimmed == "SHOW GRANTS" {
		return &TranslationResult{
			Query: `SELECT 
				grantee AS "User",
				privilege_type AS "Privilege",
				table_schema || '.' || table_name AS "On"
			FROM information_schema.role_table_grants 
			WHERE grantee = current_user`,
		}, nil
	}

	// SHOW GRANTS FOR user
	showGrantsForRe := regexp.MustCompile(`(?i)^SHOW\s+GRANTS\s+FOR\s+'?(\w+)'?(@'?[^']*'?)?$`)
	if matches := showGrantsForRe.FindStringSubmatch(trimmedInput); matches != nil {
		userName := matches[1]
		return &TranslationResult{
			Query: fmt.Sprintf(`SELECT 
				grantee AS "User",
				privilege_type AS "Privilege",
				table_schema || '.' || table_name AS "On"
			FROM information_schema.role_table_grants 
			WHERE grantee = '%s'`, userName),
		}, nil
	}

	// SHOW TABLE STATUS
	if upperTrimmed == "SHOW TABLE STATUS" {
		return &TranslationResult{
			Query: `SELECT 
				relname AS "Name",
				CASE relkind WHEN 'r' THEN 'BASE TABLE' WHEN 'v' THEN 'VIEW' END AS "Engine",
				pg_size_pretty(pg_total_relation_size(oid)) AS "Data_length",
				n_live_tup AS "Rows"
			FROM pg_stat_user_tables 
			JOIN pg_class ON relname = pg_stat_user_tables.relname
			WHERE schemaname = 'public'`,
		}, nil
	}

	// SHOW SCHEMAS
	if upperTrimmed == "SHOW SCHEMAS" {
		return &TranslationResult{
			Query: `SELECT schema_name AS "Database" 
					FROM information_schema.schemata 
					ORDER BY schema_name`,
		}, nil
	}

	// SHOW TRIGGERS
	if upperTrimmed == "SHOW TRIGGERS" {
		return &TranslationResult{
			Query: `SELECT 
				trigger_name AS "Trigger",
				event_manipulation AS "Event",
				event_object_table AS "Table",
				action_statement AS "Statement",
				action_timing AS "Timing"
			FROM information_schema.triggers 
			WHERE trigger_schema = 'public'`,
		}, nil
	}

	// SHOW FUNCTION STATUS / SHOW PROCEDURE STATUS
	if upperTrimmed == "SHOW FUNCTION STATUS" || upperTrimmed == "SHOW PROCEDURE STATUS" {
		return &TranslationResult{
			Query: `SELECT 
				routine_name AS "Name",
				routine_type AS "Type",
				routine_schema AS "Db",
				external_language AS "Language"
			FROM information_schema.routines 
			WHERE routine_schema = 'public'`,
		}, nil
	}

	// USE database
	useDbRe := regexp.MustCompile(`(?i)^USE\s+(\w+)$`)
	if matches := useDbRe.FindStringSubmatch(trimmedInput); matches != nil {
		return &TranslationResult{
			IsSpecial:   true,
			SpecialType: "use_database",
			Args:        []string{matches[1]},
		}, nil
	}

	// SHOW ENGINES (PostgreSQL doesn't have storage engines)
	if upperTrimmed == "SHOW ENGINES" {
		return &TranslationResult{
			Query: `SELECT 
				'PostgreSQL' AS "Engine",
				'DEFAULT' AS "Support",
				'PostgreSQL native storage' AS "Comment"`,
		}, nil
	}

	// SHOW CHARSET / SHOW CHARACTER SET
	if upperTrimmed == "SHOW CHARSET" || upperTrimmed == "SHOW CHARACTER SET" {
		return &TranslationResult{
			Query: `SELECT 
				pg_encoding_to_char(encoding) AS "Charset",
				pg_encoding_to_char(encoding) AS "Description",
				'UTF-8' AS "Default collation"
			FROM pg_database 
			WHERE datname = current_database()`,
		}, nil
	}

	// SHOW COLLATION
	if upperTrimmed == "SHOW COLLATION" {
		return &TranslationResult{
			Query: `SELECT 
				collname AS "Collation",
				'utf8' AS "Charset"
			FROM pg_collation 
			LIMIT 50`,
		}, nil
	}

	// SHOW WARNINGS / SHOW ERRORS (PostgreSQL doesn't have these)
	if upperTrimmed == "SHOW WARNINGS" || upperTrimmed == "SHOW ERRORS" {
		return &TranslationResult{
			Query: `SELECT 'Note' AS "Level", 0 AS "Code", 'PostgreSQL does not store warnings/errors like MySQL' AS "Message"`,
		}, nil
	}

	// SELECT DATABASE()
	if upperTrimmed == "SELECT DATABASE()" {
		return &TranslationResult{
			Query: "SELECT current_database() AS \"database()\"",
		}, nil
	}

	// SELECT VERSION()
	if upperTrimmed == "SELECT VERSION()" {
		return &TranslationResult{
			Query: "SELECT version() AS \"version()\"",
		}, nil
	}

	// SELECT USER() / SELECT CURRENT_USER()
	if upperTrimmed == "SELECT USER()" || upperTrimmed == "SELECT CURRENT_USER()" {
		return &TranslationResult{
			Query: "SELECT current_user AS \"user()\"",
		}, nil
	}

	// SELECT NOW()
	if upperTrimmed == "SELECT NOW()" {
		return &TranslationResult{
			Query: "SELECT now() AS \"now()\"",
		}, nil
	}

	// Handle PostgreSQL backslash commands (translate to MySQL equivalents)
	if strings.HasPrefix(input, "\\") {
		return t.translateBackslashCommand(input)
	}

	// No translation needed, return as-is
	return &TranslationResult{Query: input}, nil
}

func (t *Translator) translateBackslashCommand(input string) (*TranslationResult, error) {
	input = strings.TrimSpace(input)
	parts := strings.Fields(input)
	cmd := parts[0]

	switch cmd {
	case "\\l", "\\list":
		// List databases
		return &TranslationResult{
			Query: "SELECT datname AS \"Database\" FROM pg_database WHERE datistemplate = false ORDER BY datname",
		}, nil

	case "\\dt":
		// List tables
		return &TranslationResult{
			Query: `SELECT tablename AS "Tables" FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename`,
		}, nil

	case "\\dt+":
		// List tables with size
		return &TranslationResult{
			Query: `SELECT 
				tablename AS "Name",
				pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS "Size"
			FROM pg_tables 
			WHERE schemaname = 'public' 
			ORDER BY tablename`,
		}, nil

	case "\\d":
		if len(parts) > 1 {
			// Describe table
			tableName := parts[1]
			return &TranslationResult{
				Query: fmt.Sprintf(`SELECT 
					column_name AS "Column",
					data_type AS "Type",
					CASE WHEN is_nullable = 'YES' THEN 'YES' ELSE 'NO' END AS "Nullable"
				FROM information_schema.columns 
				WHERE table_schema = 'public' AND table_name = '%s'
				ORDER BY ordinal_position`, tableName),
			}, nil
		}
		// List all relations
		return &TranslationResult{
			Query: `SELECT tablename AS "Name", 'table' AS "Type" FROM pg_tables WHERE schemaname = 'public'
					UNION ALL
					SELECT viewname AS "Name", 'view' AS "Type" FROM pg_views WHERE schemaname = 'public'
					ORDER BY "Name"`,
		}, nil

	case "\\di":
		// List indexes
		return &TranslationResult{
			Query: `SELECT indexname AS "Index", tablename AS "Table" FROM pg_indexes WHERE schemaname = 'public'`,
		}, nil

	case "\\dv":
		// List views
		return &TranslationResult{
			Query: `SELECT viewname AS "View" FROM pg_views WHERE schemaname = 'public'`,
		}, nil

	case "\\df":
		// List functions
		return &TranslationResult{
			Query: `SELECT routine_name AS "Function", data_type AS "Return Type" 
					FROM information_schema.routines 
					WHERE routine_schema = 'public' AND routine_type = 'FUNCTION'`,
		}, nil

	case "\\du":
		// List users/roles
		return &TranslationResult{
			Query: `SELECT rolname AS "Role", 
					CASE WHEN rolsuper THEN 'Superuser' ELSE '' END AS "Attributes"
					FROM pg_roles ORDER BY rolname`,
		}, nil

	case "\\dn":
		// List schemas
		return &TranslationResult{
			Query: `SELECT schema_name AS "Schema" FROM information_schema.schemata ORDER BY schema_name`,
		}, nil

	case "\\c", "\\connect":
		if len(parts) > 1 {
			return &TranslationResult{
				IsSpecial:   true,
				SpecialType: "use_database",
				Args:        []string{parts[1]},
			}, nil
		}
		return nil, fmt.Errorf("usage: \\c database_name")

	case "\\q", "\\quit":
		return &TranslationResult{
			IsSpecial:   true,
			SpecialType: "quit",
		}, nil

	case "\\?", "\\help":
		return &TranslationResult{
			IsSpecial:   true,
			SpecialType: "help",
		}, nil

	case "\\x":
		return &TranslationResult{
			IsSpecial:   true,
			SpecialType: "toggle_expanded",
		}, nil

	default:
		return nil, fmt.Errorf("unknown command: %s", cmd)
	}
}
