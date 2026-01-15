package translator

import (
	"strings"
	"testing"

	"gomypg/internal/db"
)

func TestTranslateShowDatabases(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("SHOW DATABASES;")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "pg_database") {
		t.Errorf("expected query to contain pg_database, got: %s", result.Query)
	}
}

func TestTranslateShowTables(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("SHOW TABLES;")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "pg_tables") {
		t.Errorf("expected query to contain pg_tables, got: %s", result.Query)
	}
}

func TestTranslateDesc(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("DESC users")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "information_schema.columns") {
		t.Errorf("expected query to contain information_schema.columns, got: %s", result.Query)
	}
	if !strings.Contains(result.Query, "users") {
		t.Errorf("expected query to contain table name 'users', got: %s", result.Query)
	}
}

func TestTranslateShowProcesslist(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("SHOW PROCESSLIST")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "pg_stat_activity") {
		t.Errorf("expected query to contain pg_stat_activity, got: %s", result.Query)
	}
}

func TestTranslateUseDatabase(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("USE testdb")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !result.IsSpecial {
		t.Error("expected IsSpecial to be true")
	}
	if result.SpecialType != "use_database" {
		t.Errorf("expected SpecialType to be 'use_database', got: %s", result.SpecialType)
	}
	if len(result.Args) != 1 || result.Args[0] != "testdb" {
		t.Errorf("expected Args to be ['testdb'], got: %v", result.Args)
	}
}

func TestTranslateBackslashCommands(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	tests := []struct {
		input    string
		contains string
	}{
		{"\\l", "pg_database"},
		{"\\dt", "pg_tables"},
		{"\\d users", "information_schema.columns"},
		{"\\di", "pg_indexes"},
		{"\\dv", "pg_views"},
		{"\\du", "pg_roles"},
		{"\\dn", "information_schema.schemata"},
	}
	
	for _, tt := range tests {
		result, err := tr.Translate(tt.input)
		if err != nil {
			t.Errorf("unexpected error for %s: %v", tt.input, err)
			continue
		}
		if !strings.Contains(result.Query, tt.contains) {
			t.Errorf("for %s: expected query to contain %s, got: %s", tt.input, tt.contains, result.Query)
		}
	}
}

func TestMySQLNoTranslation(t *testing.T) {
	tr := New(db.MySQL)
	
	input := "SHOW DATABASES;"
	result, err := tr.Translate(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if result.Query != input {
		t.Errorf("expected no translation for MySQL, got: %s", result.Query)
	}
}

func TestTranslateShowVariablesLike(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("SHOW VARIABLES LIKE 'max%'")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "pg_settings") {
		t.Errorf("expected query to contain pg_settings, got: %s", result.Query)
	}
}

func TestTranslateShowIndex(t *testing.T) {
	tr := New(db.PostgreSQL)
	
	result, err := tr.Translate("SHOW INDEX FROM users")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	
	if !strings.Contains(result.Query, "pg_indexes") {
		t.Errorf("expected query to contain pg_indexes, got: %s", result.Query)
	}
	if !strings.Contains(result.Query, "users") {
		t.Errorf("expected query to contain 'users', got: %s", result.Query)
	}
}
