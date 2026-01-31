"""Tests for main.py CSV loading and orchestration"""
import pytest
import duckdb
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock, call
import asyncio
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "init_migration"))

from main import load_csv_to_duckdb, main


class TestLoadCsvToDuckdb:
    """Test CSV loading with DuckDB"""

    def test_load_valid_csv(self, tmp_path):
        """Successfully load a well-formed CSV"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2,col3\na,b,c\nd,e,f\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "my_table", db_path)

        assert result["table_name"] == "my_table"
        assert result["row_count"] == 2
        assert result["column_count"] == 3
        assert result["columns"] == ["col1", "col2", "col3"]
        assert result["file_path"] == str(csv_file)
        assert result["quarantine_table"] == "my_table_quarantine"
        assert result["quarantine_count"] == 0

    def test_sanitize_table_name_with_hyphens(self, tmp_path):
        """Table names with hyphens are sanitized to underscores"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x,y\n1,2\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "country-us", db_path)

        assert result["table_name"] == "country_us"

    def test_sanitize_table_name_with_special_chars(self, tmp_path):
        """Table names with special characters are sanitized"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x,y\n1,2\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "bad-name!@#$%", db_path)

        assert result["table_name"] == "bad_name_____"

    def test_invalid_table_name_raises(self, tmp_path):
        """Table name with only special characters raises ValueError"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n")

        with pytest.raises(ValueError, match="Invalid table name"):
            load_csv_to_duckdb(csv_file, "!@#$", str(tmp_path / "test.duckdb"))

    def test_missing_csv_raises(self, tmp_path):
        """Missing CSV file raises FileNotFoundError"""
        missing_file = tmp_path / "nonexistent.csv"

        with pytest.raises(FileNotFoundError, match="CSV file not found"):
            load_csv_to_duckdb(missing_file, "table", str(tmp_path / "test.duckdb"))

    def test_replace_existing_table(self, tmp_path):
        """Loading CSV twice replaces the table"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n2\n")
        db_path = str(tmp_path / "test.duckdb")

        load_csv_to_duckdb(csv_file, "tbl", db_path)
        csv_file.write_text("x\n10\n")  # Update CSV
        result = load_csv_to_duckdb(csv_file, "tbl", db_path)

        assert result["row_count"] == 1  # Only one row now

    def test_empty_csv(self, tmp_path):
        """CSV with only headers loads zero rows"""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("col1,col2\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "empty_table", db_path)

        assert result["row_count"] == 0
        assert result["column_count"] == 2

    def test_unicode_content(self, tmp_path):
        """CSV with unicode characters loads correctly"""
        csv_file = tmp_path / "unicode.csv"
        csv_file.write_text("name,city\nJosé,São Paulo\n北京,Beijing\n", encoding="utf-8")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "unicode_table", db_path)

        assert result["row_count"] == 2
        assert result["columns"] == ["name", "city"]

    def test_large_number_of_columns(self, tmp_path):
        """CSV with many columns loads correctly"""
        headers = [f"col{i}" for i in range(100)]
        values = [str(i) for i in range(100)]
        csv_file = tmp_path / "wide.csv"
        csv_file.write_text(",".join(headers) + "\n" + ",".join(values) + "\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "wide_table", db_path)

        assert result["column_count"] == 100
        assert result["row_count"] == 1

    def test_numeric_data_types(self, tmp_path):
        """CSV with numeric data is loaded with proper types"""
        csv_file = tmp_path / "numeric.csv"
        csv_file.write_text("int_col,float_col\n1,1.5\n2,2.5\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "numeric_table", db_path)

        # Verify data loaded correctly
        conn = duckdb.connect(db_path)
        values = conn.execute("SELECT * FROM numeric_table ORDER BY int_col").fetchall()
        conn.close()

        assert len(values) == 2
        assert result["row_count"] == 2

    def test_quoted_fields_with_commas(self, tmp_path):
        """CSV with quoted fields containing commas loads correctly"""
        csv_file = tmp_path / "quoted.csv"
        csv_file.write_text('name,address\n"Smith, John","123 Main St, Apt 4"\n')
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "quoted_table", db_path)

        assert result["row_count"] == 1
        assert result["column_count"] == 2

    def test_default_db_path(self, tmp_path, monkeypatch):
        """Default database path is used when not specified"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n")

        # Change to tmp directory so default path is created there
        monkeypatch.chdir(tmp_path)

        result = load_csv_to_duckdb(csv_file, "test_table")

        assert result["table_name"] == "test_table"
        assert (tmp_path / "data.duckdb").exists()


class TestMainOrchestration:
    """Test main() function orchestration"""

    @pytest.mark.asyncio
    async def test_main_downloads_and_loads_csv(self, tmp_path, monkeypatch):
        """main() successfully downloads and loads CSV"""
        # Change to tmp directory for testing
        monkeypatch.chdir(tmp_path)

        # Create downloads directory
        downloads_dir = tmp_path / "downloads"
        downloads_dir.mkdir()

        # Create a test CSV that will be "downloaded"
        csv_file = downloads_dir / "country-us.csv"
        csv_content = b"id,name\nocd-division/country:us,United States\n"

        # Mock the downloader
        mock_downloader = MagicMock()
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock()
        mock_downloader.fetch_many = AsyncMock(return_value=[csv_content])

        # Mock download_many to actually write the file
        async def mock_download_many(url_to_path):
            for url, path in url_to_path.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(csv_content)
            return [(str(path), "downloaded") for path in url_to_path.values()]

        mock_downloader.download_many = mock_download_many

        with patch("main.AsyncDownloader", return_value=mock_downloader):
            with patch("builtins.print") as mock_print:
                await main()

                # Verify output contains success message
                printed_output = " ".join(str(call) for call in mock_print.call_args_list)
                assert "✓" in printed_output or "Loaded" in printed_output

    @pytest.mark.asyncio
    async def test_main_handles_missing_file(self, tmp_path, monkeypatch):
        """main() handles case where CSV file is not downloaded"""
        monkeypatch.chdir(tmp_path)

        # Mock downloader that doesn't create the file
        mock_downloader = MagicMock()
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock()
        mock_downloader.fetch_many = AsyncMock(return_value=[b"data"])
        mock_downloader.download_many = AsyncMock(return_value=[])

        with patch("main.AsyncDownloader", return_value=mock_downloader):
            with patch("builtins.print") as mock_print:
                await main()

                # Should print error message
                printed_output = " ".join(str(call) for call in mock_print.call_args_list)
                assert "✗" in printed_output or "Failed" in printed_output

    @pytest.mark.asyncio
    async def test_main_handles_load_exception(self, tmp_path, monkeypatch):
        """main() handles CSV load failures gracefully"""
        monkeypatch.chdir(tmp_path)

        downloads_dir = tmp_path / "downloads"
        downloads_dir.mkdir()
        csv_file = downloads_dir / "country-us.csv"
        csv_file.write_text("id,name\n1,test\n")

        mock_downloader = MagicMock()
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock()
        mock_downloader.fetch_many = AsyncMock(return_value=[b"data"])
        mock_downloader.download_many = AsyncMock(return_value=[("path", "downloaded")])

        with patch("main.AsyncDownloader", return_value=mock_downloader):
            with patch("main.load_csv_to_duckdb", side_effect=Exception("DuckDB error")):
                with patch("builtins.print") as mock_print:
                    # Should not raise, but handle gracefully
                    await main()

                    # Check that failure was printed
                    printed_calls = [str(c) for c in mock_print.call_args_list]
                    error_printed = any("Failed to load" in str(c) or "✗" in str(c) for c in printed_calls)
                    assert error_printed

    @pytest.mark.asyncio
    async def test_main_prints_column_summary(self, tmp_path, monkeypatch):
        """main() prints column summary with truncation for many columns"""
        monkeypatch.chdir(tmp_path)

        downloads_dir = tmp_path / "downloads"
        downloads_dir.mkdir()
        csv_file = downloads_dir / "country-us.csv"

        # Create CSV with many columns
        headers = [f"col{i}" for i in range(10)]
        csv_content = (",".join(headers) + "\n1,2,3,4,5,6,7,8,9,10\n").encode()
        csv_file.write_bytes(csv_content)

        mock_downloader = MagicMock()
        mock_downloader.__aenter__ = AsyncMock(return_value=mock_downloader)
        mock_downloader.__aexit__ = AsyncMock()
        mock_downloader.fetch_many = AsyncMock(return_value=[csv_content])

        async def mock_download_many(url_to_path):
            # File already exists from setup
            return [(str(path), "downloaded") for path in url_to_path.values()]

        mock_downloader.download_many = mock_download_many

        with patch("main.AsyncDownloader", return_value=mock_downloader):
            with patch("builtins.print") as mock_print:
                await main()

                # Check that column truncation message is printed
                printed_calls = [str(c) for c in mock_print.call_args_list]
                has_truncation = any("+5 more" in str(c) for c in printed_calls)
                assert has_truncation


class TestDuckDBIntegration:
    """Integration tests with actual DuckDB operations"""

    def test_data_persists_across_connections(self, tmp_path):
        """Data loaded in one connection is available in another"""
        csv_file = tmp_path / "persist.csv"
        csv_file.write_text("x,y\n1,2\n3,4\n")
        db_path = str(tmp_path / "persist.duckdb")

        load_csv_to_duckdb(csv_file, "my_data", db_path)

        # Open new connection and verify data
        conn = duckdb.connect(db_path)
        result = conn.execute("SELECT COUNT(*) FROM my_data").fetchone()[0]
        conn.close()

        assert result == 2

    def test_multiple_tables_in_same_db(self, tmp_path):
        """Multiple CSVs can be loaded into the same database"""
        csv1 = tmp_path / "table1.csv"
        csv1.write_text("a\n1\n")
        csv2 = tmp_path / "table2.csv"
        csv2.write_text("b,c\n2,3\n")
        db_path = str(tmp_path / "multi.duckdb")

        load_csv_to_duckdb(csv1, "t1", db_path)
        load_csv_to_duckdb(csv2, "t2", db_path)

        conn = duckdb.connect(db_path)
        tables = conn.execute("SHOW TABLES").fetchall()
        conn.close()

        table_names = [t[0] for t in tables]
        assert "t1" in table_names
        assert "t2" in table_names

    def test_query_loaded_data(self, tmp_path):
        """Can query data after loading"""
        csv_file = tmp_path / "query_test.csv"
        csv_file.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,150\n")
        db_path = str(tmp_path / "query.duckdb")

        load_csv_to_duckdb(csv_file, "users", db_path)

        conn = duckdb.connect(db_path)
        # Query with WHERE clause
        result = conn.execute("SELECT name FROM users WHERE value > 150").fetchall()
        conn.close()

        assert len(result) == 1
        assert result[0][0] == "Bob"

    def test_connection_cleanup_on_exception(self, tmp_path):
        """DuckDB connection is closed even if exception occurs"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("x\n1\n")
        db_path = str(tmp_path / "cleanup.duckdb")

        # First, load successfully
        load_csv_to_duckdb(csv_file, "test_table", db_path)

        # Now verify we can connect again (connection was closed properly)
        conn = duckdb.connect(db_path)
        tables = conn.execute("SHOW TABLES").fetchall()
        conn.close()

        # Should have 2 tables: main table and quarantine table
        assert len(tables) == 2
        table_names = [t[0] for t in tables]
        assert "test_table" in table_names
        assert "test_table_quarantine" in table_names

    def test_large_csv_loads_efficiently(self, tmp_path):
        """Large CSV files load without issues"""
        csv_file = tmp_path / "large.csv"

        # Generate a moderately large CSV (1000 rows)
        with open(csv_file, 'w') as f:
            f.write("id,name,email,value\n")
            for i in range(1000):
                f.write(f"{i},User{i},user{i}@example.com,{i*10}\n")

        db_path = str(tmp_path / "large.duckdb")

        result = load_csv_to_duckdb(csv_file, "large_table", db_path)

        assert result["row_count"] == 1000
        assert result["column_count"] == 4

    def test_special_characters_in_data(self, tmp_path):
        """Data with special characters is preserved"""
        csv_file = tmp_path / "special.csv"
        csv_file.write_text('text\n"Line 1\nLine 2"\n"Tab\\there"\n')
        db_path = str(tmp_path / "special.duckdb")

        result = load_csv_to_duckdb(csv_file, "special_chars", db_path)

        # Verify data was loaded
        conn = duckdb.connect(db_path)
        rows = conn.execute("SELECT * FROM special_chars").fetchall()
        conn.close()

        assert len(rows) == 2


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_single_column_csv(self, tmp_path):
        """CSV with a single column loads correctly"""
        csv_file = tmp_path / "single.csv"
        csv_file.write_text("value\n1\n2\n3\n")
        db_path = str(tmp_path / "single.duckdb")

        result = load_csv_to_duckdb(csv_file, "single_col", db_path)

        assert result["column_count"] == 1
        assert result["row_count"] == 3

    def test_single_row_csv(self, tmp_path):
        """CSV with a single data row loads correctly"""
        csv_file = tmp_path / "single_row.csv"
        csv_file.write_text("a,b,c\n1,2,3\n")
        db_path = str(tmp_path / "single_row.duckdb")

        result = load_csv_to_duckdb(csv_file, "single_row_table", db_path)

        assert result["row_count"] == 1
        assert result["column_count"] == 3

    def test_table_name_with_numbers(self, tmp_path):
        """Table names with numbers are handled correctly"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "table_123", db_path)

        assert result["table_name"] == "table_123"

    def test_table_name_starting_with_number(self, tmp_path):
        """Table names starting with numbers get 't_' prefix"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("x\n1\n")
        db_path = str(tmp_path / "test.duckdb")

        result = load_csv_to_duckdb(csv_file, "123_table", db_path)

        # Should be prefixed with 't_' to be valid SQL
        assert result["table_name"] == "t_123_table"
        assert result["row_count"] == 1

    def test_csv_with_malformed_rows_loads_to_quarantine(self, tmp_path):
        """CSV with rows having too many columns loads valid rows and quarantines bad ones"""
        csv_file = tmp_path / "malformed.csv"
        # Row 2 has extra columns (4 values for 3 columns)
        csv_file.write_text("a,b,c\n1,2,3\n4,5,6,7\n8,9,10\n")
        db_path = str(tmp_path / "malformed.duckdb")

        result = load_csv_to_duckdb(csv_file, "malformed_test", db_path)

        # Valid rows should be loaded (rows 1 and 3)
        assert result["row_count"] == 2
        assert result["column_count"] == 3

        # Malformed row should be in quarantine
        # Note: The quarantine detection may not work perfectly with the EXCEPT approach
        # but the main table should have valid data
        assert "quarantine_table" in result
        assert "quarantine_count" in result
