import argparse
import logging
from pathlib import Path
import pandas as pd
import csv # For more granular reading if needed
import shutil # For replacing the file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_header_row(file_path, expected_markers):
    """
    Attempts to find the 0-based index of the header row in a CSV file.

    Args:
        file_path (Path): Path to the CSV file.
        expected_markers (list): A list of column names expected to be in the header.

    Returns:
        int: The 0-based index of the header row, or -1 if not found or error occurs.
    """
    logging.debug(f"Attempting to find header in {file_path} using markers: {expected_markers}")
    # Try common encodings
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'iso-8859-1']
    detected_encoding = None
    header_row_index = -1

    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                # Use csv reader for more control over quoting/delimiters if needed
                # For now, simple line reading is okay
                for i, line in enumerate(f):
                    line_content = line.strip()
                    # Skip empty lines
                    if not line_content:
                        continue
                    # Basic checks: contains commas, contains markers
                    if ',' in line_content:
                        # Check if all markers are present (case-insensitive)
                        line_lower = line_content.lower()
                        if all(marker.lower() in line_lower for marker in expected_markers):
                            # Perform a more robust check with pandas sniffing
                            try:
                                # Try reading just this line as header to validate columns
                                df_header_test = pd.read_csv(file_path, header=i, nrows=0, encoding=enc)
                                df_header_test.columns = df_header_test.columns.str.replace('^\\ufeff', '', regex=True).str.strip() # Clean potential BOM
                                if all(marker in df_header_test.columns for marker in expected_markers):
                                    logging.info(f"Confirmed header on line {i+1} (index {i}) in {file_path} using encoding '{enc}'. Markers: {expected_markers}")
                                    header_row_index = i
                                    detected_encoding = enc
                                    break # Found header
                                else:
                                     logging.debug(f"Line {i+1} contained markers but pandas validation failed. Found columns: {df_header_test.columns.tolist()}")

                            except Exception as pd_err:
                                logging.debug(f"Pandas validation failed for line {i+1} in {file_path} with encoding {enc}: {pd_err}")
                                continue # Try next line
                        # else: # Optional: log lines that have commas but not all markers
                            # logging.debug(f"Line {i+1} did not contain all markers '{expected_markers}'.")
            if header_row_index != -1:
                break # Stop trying encodings if header found
        except UnicodeDecodeError:
            logging.warning(f"Encoding {enc} failed for {file_path}, trying next...")
            continue
        except Exception as file_read_error:
            logging.error(f"Unexpected error reading {file_path} with encoding {enc}: {file_read_error}")
            return -1 # Indicate error

    if header_row_index == -1:
        logging.warning(f"Could not reliably find header row in {file_path} using markers {expected_markers}.")

    return header_row_index

def clean_csv_metadata(file_path, header_index):
    """
    Reads a CSV starting from the header row and overwrites the original file
    using basic file I/O to avoid pandas parsing errors during cleanup.

    Args:
        file_path (Path): Path to the CSV file.
        header_index (int): 0-based index of the header row.

    Returns:
        bool: True if successful, False otherwise.
    """
    logging.info(f"Cleaning metadata from {file_path} (header found at index {header_index}) using basic I/O...")
    temp_file_path = file_path.with_suffix(file_path.suffix + '.tmp')

    try:
        # Determine the original encoding if possible (using find_header_row logic again briefly)
        # This is slightly redundant but ensures we read correctly
        original_encoding = 'utf-8-sig' # Default
        encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'iso-8859-1']
        for enc in encodings_to_try:
            try:
                 with open(file_path, 'r', encoding=enc) as f_check:
                     f_check.readline() # Try reading one line
                 original_encoding = enc
                 logging.debug(f"Determined encoding '{original_encoding}' for reading {file_path}")
                 break
            except UnicodeDecodeError:
                 continue
            except Exception:
                 pass # Ignore other errors during encoding check

        with open(file_path, 'r', encoding=original_encoding) as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile: # Write standard UTF-8

            # Skip lines before the header
            for _ in range(header_index):
                next(infile)

            # Read header and remaining lines, write to temp file
            shutil.copyfileobj(infile, outfile)

        # Replace original file with the temp file
        shutil.move(str(temp_file_path), str(file_path))
        logging.info(f"Successfully cleaned and overwrote {file_path}.")
        return True

    except Exception as e:
        logging.error(f"Failed to clean or overwrite {file_path} using basic I/O: {e}", exc_info=True)
        # Clean up temp file if it exists
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                logging.error(f"Could not remove temporary file: {temp_file_path}")
        return False
    finally:
         # Ensure temp file is removed in case of unexpected exit before move
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
                logging.debug(f"Removed leftover temp file: {temp_file_path}")
            except OSError:
                 # Log if removal fails but don't stop the process
                 logging.error(f"Could not remove temporary file during final cleanup: {temp_file_path}")

def clean_summary_csv(file_path):
    """
    Cleans the summary.csv file which has two sections (conversation and question summaries)
    by creating a single combined header and concatenating the data.

    Args:
        file_path (Path): Path to the summary.csv file.

    Returns:
        bool: True if successful, False otherwise.
    """
    logging.info(f"Attempting special cleaning for {file_path}...")
    header1_markers = ['Conversation ID', 'Conversation Title']
    header2_markers = ['Question ID', 'Question Type'] # Use simpler markers for second header
    header1_idx = -1
    header2_idx = -1

    # --- Find header indices --- # Simplified check implemented
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'iso-8859-1']
    detected_encoding = 'utf-8-sig' # Assume default initially
    try:
        # Find header 1
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    for i, line in enumerate(f):
                        # Simplified check: contains markers and at least 3 commas
                        if all(m.lower() in line.lower() for m in header1_markers) and line.count(',') >= 3:
                            header1_idx = i
                            detected_encoding = enc
                            logging.info(f"Found summary header 1 at index {header1_idx} with encoding {detected_encoding} (simplified check)")
                            break
                if header1_idx != -1:
                    break
            except UnicodeDecodeError:
                continue

        if header1_idx == -1:
            logging.error(f"Could not find summary header 1 using markers {header1_markers} in {file_path}")
            return False

        # Find header 2 (starting search after header 1)
        header2_search_start_line = header1_idx + 1
        with open(file_path, 'r', encoding=detected_encoding) as f:
             # Skip lines up to the start point
             for _ in range(header2_search_start_line):
                 next(f)
             # Search remaining lines
             for i, line in enumerate(f, start=header2_search_start_line):
                 # Simplified check: contains markers and at least 2 commas
                 if all(m.lower() in line.lower() for m in header2_markers) and line.count(',') >= 2:
                     header2_idx = i
                     logging.info(f"Found summary header 2 at index {header2_idx} (simplified check)")
                     break

        if header2_idx == -1:
             logging.error(f"Could not find summary header 2 using markers {header2_markers} after index {header1_idx} in {file_path}")
             # Decide if we should proceed without question summaries or fail
             # For now, let's fail if the structure isn't as expected.
             return False

    except Exception as e:
        logging.error(f"Error finding headers in {file_path}: {e}")
        return False

    # --- Read necessary lines manually using determined encoding ---
    try:
        lines = []
        with open(file_path, 'r', encoding=detected_encoding) as f:
            lines = f.readlines()

        if not lines or len(lines) <= header2_idx:
             logging.error(f"File {file_path} seems too short or headers not found correctly.")
             return False

        header1_line = lines[header1_idx].strip()
        conv_data_line = lines[header1_idx + 1].strip() # Assume one data line for conv summary
        header2_line = lines[header2_idx].strip()
        question_data_lines = [line.strip() for line in lines[header2_idx+1:] if line.strip()] # Get non-empty question data lines

    except Exception as e:
         logging.error(f"Error reading lines manually from {file_path}: {e}")
         return False

    # --- Check if already cleaned (to the 4-column format) ---
    target_cols = ['ID', 'Type', 'Text', 'Summary']
    try:
        df_check = pd.read_csv(file_path, nrows=0, encoding=detected_encoding)
        # Use header1_line to check if it *looks* like the target header
        # This check is imperfect but better than just checking header1_idx == 0
        if header1_idx == 0 and "ID" in header1_line and "Type" in header1_line and "Text" in header1_line and "Summary" in header1_line:
            df_check.columns = df_check.columns.str.replace('^\\ufeff', '', regex=True).str.strip()
            if list(df_check.columns) == target_cols:
                logging.info(f"{file_path} already appears to be cleaned to the target 4-column format. Skipping.")
                return True
        elif header1_idx == 0: # Header is at line 1, but not the target format
             # Header 1 is at line 1, but it's not the target format. Proceed with cleaning.
             logging.info("Header 1 found at line 1, but not the target format. Proceeding with cleaning.")
        # else: header1_idx > 0, needs cleaning

    except Exception as e:
         logging.error(f"Error checking if {file_path} is already cleaned: {e}. Proceeding with cleaning attempt.")

    # --- Process the data to the 4-column format using manual parsing --- #
    try:
        # Parse conversation summary section using csv module
        conv_reader = csv.reader([header1_line, conv_data_line])
        conv_header = [h.strip() for h in next(conv_reader)]
        conv_data = next(conv_reader)

        # Create df_conv from parsed data
        conv_data_dict = dict(zip(conv_header, conv_data))
        df_conv = pd.DataFrame({
            'ID': [conv_data_dict.get('Conversation ID')],
            'Type': ['Conversation'],
            'Text': [conv_data_dict.get('Conversation Title')],
            'Summary': [conv_data_dict.get('Conversation Summary')]
        })

        # Parse question summary section (header + data lines) using csv module
        if question_data_lines:
            quest_reader = csv.reader([header2_line] + question_data_lines)
            quest_header = [h.strip() for h in next(quest_reader)]
            quest_data = list(quest_reader)

            # Create df_quest from parsed data
            df_quest_raw = pd.DataFrame(quest_data, columns=quest_header)

            required_quest_cols = ['Question ID', 'Question Type', 'Question Text', 'Question Summary']
            if not all(col in df_quest_raw.columns for col in required_quest_cols):
                logging.error(f"Missing expected columns after parsing question summary section of {file_path}. Found: {df_quest_raw.columns.tolist()}")
                return False

            df_quest = pd.DataFrame({
                'ID': df_quest_raw['Question ID'],
                'Type': df_quest_raw['Question Type'],
                'Text': df_quest_raw['Question Text'],
                'Summary': df_quest_raw['Question Summary']
            })
        else:
             df_quest = pd.DataFrame(columns=target_cols) # Empty if no question lines


        # Concatenate
        df_final = pd.concat([df_conv, df_quest], ignore_index=True)

        # Ensure final columns match target
        if list(df_final.columns) != target_cols:
             # This shouldn't happen if logic above is correct, but check anyway
             logging.warning(f"Final columns {df_final.columns.tolist()} don\'t match target {target_cols}. Reordering.")
             df_final = df_final[target_cols]

        # Overwrite the original file
        df_final.to_csv(file_path, index=False, encoding='utf-8')
        logging.info(f"Successfully cleaned and overwrote {file_path} to 4-column format.")
        return True

    except KeyError as e:
         logging.error(f"Missing expected column during transformation of {file_path}: {e}", exc_info=True)

def main(args):
    gd_number = args.gd_number
    data_dir = Path("./Data") / f"GD{gd_number}"

    if not data_dir.is_dir():
        logging.error(f"Data directory not found: {data_dir}")
        return

    logging.info(f"Starting metadata cleanup for GD{gd_number} in {data_dir}")

    # Define files to check and their key header markers
    # Exclude aggregate.csv (handled by preprocess_aggregate.py)
    # Exclude *_standardized.csv, *_report.csv etc.
    files_to_clean = {
        f"GD{gd_number}_participants.csv": ['Participant Id', 'Sample Provider Id'],
        f"GD{gd_number}_discussion_guide.csv": ['Item type (dropdown)', 'Content'],
        f"GD{gd_number}_binary.csv": ['Question ID', 'Participant ID', 'Thought ID', 'Vote'],
        f"GD{gd_number}_preference.csv": ['Question ID', 'Participant ID', 'Thought A ID', 'Thought B ID', 'Vote'],
        f"GD{gd_number}_verbatim_map.csv": ['Question ID', 'Question Text', 'Participant ID', 'Thought ID', 'Thought Text'],
        f"GD{gd_number}_summary.csv": ['Conversation ID', 'Conversation Title', 'Questions Selected'],
        # Add other raw Remesh files if necessary
    }

    # Hardcoded header indices for known problematic files (0-based)
    hardcoded_headers = {
        f"GD{gd_number}_participants.csv": 11,
        f"GD{gd_number}_discussion_guide.csv": 12,
        # f"GD{gd_number}_summary.csv": 7 # Removed - handled separately
    }

    # --- Process standard files ---
    for filename, markers in files_to_clean.items():
        # Skip summary file in this loop
        if "summary.csv" in filename:
            continue

        file_path = data_dir / filename
        if file_path.exists():
            logging.info(f"Processing file: {file_path}")
            header_idx = -1
            needs_cleaning = False

            # 1. Try marker-based detection first
            detected_idx = find_header_row(file_path, markers)

            if detected_idx == 0:
                logging.info(f"Header already at line 1 (index 0) for {filename}. No cleanup needed.")
                header_idx = 0 # Mark as found at 0
            elif detected_idx > 0:
                logging.info(f"Header found at index {detected_idx} using markers. Scheduling cleanup.")
                header_idx = detected_idx
                needs_cleaning = True
            else: # detected_idx == -1 (markers didn't find it)
                logging.warning(f"Marker-based detection failed for {filename}.")
                # 2. Check if it's a file with a hardcoded index
                if filename in hardcoded_headers:
                    logging.info(f"Checking hardcoded index for {filename}.")
                    # 2a. Check if header is *already* at line 1 (index 0) even though markers failed
                    # We need a quick check here without full find_header_row logic
                    try:
                        df_check = pd.read_csv(file_path, nrows=1, encoding='utf-8-sig') # Read first line + header
                        df_check.columns = df_check.columns.str.replace('^\\ufeff', '', regex=True).str.strip()
                        if all(marker in df_check.columns for marker in markers):
                            logging.info(f"Header check confirms header is already at line 1 for {filename} (hardcoded case). No cleanup needed.")
                            header_idx = 0 # Mark as found at 0
                        else:
                            logging.warning(f"Header not at line 1 for {filename}. Using hardcoded index.")
                            header_idx = hardcoded_headers[filename]
                            needs_cleaning = True
                    except Exception as e:
                        logging.error(f"Error checking line 1 for {filename} before using hardcoded index: {e}")
                        # Fallback to assuming it needs cleaning with hardcoded index
                        logging.warning(f"Falling back to hardcoded index {hardcoded_headers[filename]} for {filename}.")
                        header_idx = hardcoded_headers[filename]
                        needs_cleaning = True
                else:
                    # Markers failed, and no hardcoded index available
                    logging.error(f"Could not find header for {filename} using markers and no hardcoded index provided. Skipping cleanup.")
                    # Keep header_idx = -1

            # 3. Perform cleanup if needed and possible
            if needs_cleaning and header_idx > 0:
                clean_csv_metadata(file_path, header_idx)
            elif not needs_cleaning and header_idx == 0:
                pass # Already clean, do nothing
            elif header_idx == -1:
                logging.error(f"Final decision: Skipping cleanup for {filename} as header could not be reliably located.")

        else:
            logging.warning(f"File not found, skipping: {file_path}")

    # --- Process the special summary.csv file ---
    summary_filename = f"GD{gd_number}_summary.csv"
    summary_file_path = data_dir / summary_filename
    if summary_file_path.exists():
        logging.info(f"Processing special file: {summary_file_path}")
        if not clean_summary_csv(summary_file_path):
             logging.error(f"Failed to clean {summary_filename}.")
    else:
        logging.warning(f"File not found, skipping: {summary_file_path}")

    logging.info(f"Metadata cleanup for GD{gd_number} completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove initial metadata rows from raw Remesh CSV files, making the header the first line.")
    parser.add_argument("--gd_number", type=int, required=True, help="Global Dialogue cadence number (e.g., 3).")
    args = parser.parse_args()
    main(args) 