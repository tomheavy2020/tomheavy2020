# Subdomain Checker

A Node.js script to check the status of multiple subdomains for a given base domain.

## Features

- Checks a list of subdomains concurrently.
- Accepts base domain and subdomain list as command-line arguments.
- Reports the status (active, error) for each subdomain.

## Prerequisites

- Node.js (v12.x or later recommended)
- npm (usually comes with Node.js)

## Setup

1.  Clone the repository (or download the `check_subdomains.js` and `package.json` files).
2.  Navigate to the directory containing the files.
3.  Install dependencies:
    ```bash
    npm install
    ```

## Usage

You can run the script with default values or provide your own.

**Default:**
Checks a predefined list of subdomains for the base domain `api2.grofers.com`.

```bash
node check_subdomains.js
```

**Custom Base Domain:**
Checks a predefined list of subdomains for a specified base domain.

```bash
node check_subdomains.js yourbasedomain.com
```
*Example:*
```bash
node check_subdomains.js example.com
```

**Custom Base Domain and Custom Subdomain List:**
Checks a custom, comma-separated list of subdomains for a specified base domain.

```bash
node check_subdomains.js yourbasedomain.com sub1,sub2,sub3
```
*Example:*
```bash
node check_subdomains.js example.com www,api,store,test
```

### Output Example

The script will output the status of each subdomain:

```
Checking subdomains for base domain: example.com
Subdomains to check: www,api,store,test

--- Scan Results ---
[https://www.example.com] - Status: active
[https://api.example.com] - Status: error (Error: Request failed with status code 404)
[https://store.example.com] - Status: active
[https://test.example.com] - Status: error (Error: connect ECONNREFUSED 127.0.0.1:443)
```

*(Note: The actual output and errors will vary based on the subdomains and their real status.)*
