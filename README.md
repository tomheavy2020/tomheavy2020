# PenTestScriptV2 - Basic Penetration Testing Tool

`PenTestScriptV2` is a simple Java-based tool for educational purposes designed to perform basic penetration testing tasks on a target domain. It includes functionalities for:

*   Port scanning for common ports.
*   HTTP/S service testing.
*   Analysis of common HTTP security headers.

## !!! IMPORTANT: ETHICAL USE ONLY !!!

*   **FOR EDUCATIONAL PURPOSES ONLY.**
*   **DO NOT USE AGAINST TARGETS WITHOUT EXPLICIT WRITTEN PERMISSION.**
*   **ALWAYS USE THIS SCRIPT RESPONSIBLY AND WITHIN LEGAL BOUNDARIES.**
*   Preferably, use this script on your own local lab environment (e.g., using "localhost" as the target) or on bug bounty programs with a clear and permissive scope.
*   Unauthorized scanning or testing of systems can lead to serious legal consequences.

## Features

*   Scans for a predefined list of common ports (e.g., 80, 443, 8080, 22, 21).
*   Identifies open HTTP/S services on the discovered ports.
*   Retrieves and displays HTTP response headers.
*   Analyzes common security headers such as:
    *   `Strict-Transport-Security` (HSTS)
    *   `X-Content-Type-Options`
    *   `X-Frame-Options`
    *   `Content-Security-Policy` (CSP)
    *   `Permissions-Policy`
    *   `Referrer-Policy`
*   Checks for informational headers like `X-Powered-By` and `Server`.
*   Includes a mechanism to bypass SSL certificate validation for testing environments with self-signed certificates (use with caution).

## Prerequisites

*   Java Development Kit (JDK) installed (version 8 or higher recommended).

## Compilation

1.  Navigate to the directory containing `PenTestScriptV2.java`.
2.  Compile the Java code using the Java compiler:

    ```bash
    javac PenTestScriptV2.java
    ```

    This will create a `PenTestScriptV2.class` file in the same directory.

## Execution

1.  After successful compilation, run the script from the command line:

    ```bash
    java PenTestScriptV2 <target_domain>
    ```

    Replace `<target_domain>` with the domain name or IP address you are authorized to test.

    **Examples:**

    *   To test a remote server (ensure you have permission!):
        ```bash
        java PenTestScriptV2 example.com
        ```
    *   To test a local server:
        ```bash
        java PenTestScriptV2 localhost
        ```

2.  If no target domain is provided, the script will display usage instructions:
    ```
    Usage: java PenTestScriptV2 <target_domain>
    Example: java PenTestScriptV2 example.com
    For local testing: java PenTestScriptV2 localhost

    IMPORTANT: Only use this script on systems you have explicit written permission to test.
    ```

## Output Interpretation

The script will output:

*   A list of open ports found on the target.
*   For each HTTP/S port:
    *   The HTTP status code.
    *   A list of response headers.
    *   An analysis of security headers, indicating whether they are present ([GOOD] or [INFO]) or missing/misconfigured ([WARN] or [INFO]).
*   For other open ports, it will attempt a basic banner grab.

Review the output carefully. The security header analysis provides insights into the web application's security posture. "[WARN]" messages indicate areas that might need attention to improve security. "[INFO]" messages provide other potentially useful details.

## Disclaimer

The creators and contributors of this script are not responsible for any misuse or damage caused by this tool. Use it at your own risk and always adhere to ethical guidelines and applicable laws.
