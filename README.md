# PHP2Shell Detection & Response Lab
A defensive security lab built around the critical PHP core vulnerabilities CVE-2026-109618 and CVE-2026-109619 ("PHP2Shell"). This project focuses on detection engineering, patch verification, and incident-response documentation.

## ⚠️ Scope & Disclaimer
This repository does **not** contain working exploit code or a proof-of-concept for CVE-2026-109618 / CVE-2026-109619. Given that both vulnerabilities are critical (CVSS v4.0: 9.2), actively discussed, and reportedly reproduced by security researchers shortly after disclosure, the goal here is purely defensive: building detection logic, verifying remediation, and documenting the incident-response process a security team would follow.

## 🧩 Background
- **Disclosed:** October 21, 2026
- **CVSS v4.0 score:** 9.2 (Critical) for both CVEs
- **Type:** Remote Code Execution (RCE) in Core PHP
- **CVE-2026-109618:** Happens when PHP runs out of memory (OOM) while handling a request. Instead of cleaning up safely, PHP unexpectedly jumps out of what it was doing (`longjmp()`) and leaves some memory behind in an unfinished, "uninitialized" state. When the *next* request comes in, PHP can accidentally read or act on that leftover memory instead of fresh data. By intentionally forcing out-of-memory conditions over and over, an attacker can turn this leftover memory into a way to run their own code on the server.
- **CVE-2026-109619:** Works the same way, but is triggered by a fatal error instead of an out-of-memory condition. When PHP aborts a request after a fatal error, it can leave a piece of memory pointing to a spot that has already been freed up ("dangling pointer"). A later request may then read from, or make decisions based on that now-invalid memory, which can also be abused to run unauthorized code on the server.
**In short:** both bugs come from the same root cause PHP not cleaning up memory properly when a request is cut short (by an OOM error or a fatal error) and both can be escalated from "memory corruption" to full remote code execution.
- **Patched in:** PHP 8.5.12, 8.4.27, 8.3.36, 8.2.35 (minimal source backports also released for 7.4, 8.0, 8.1)
- **Sources:** PHP Security Team advisory, additional analysis from watchTowr, SOC Prime, Fastly, Bitsight

## 🛠 Technology Stack
- **OS/Infrastructure:** Linux (Ubuntu Server), VMware
- **Web stack:** Apache/Nginx + php-fpm
- **Behavioral monitoring:** auditd / Falco
- **Detection engineering:** Sigma rules
- **Automation:** Python (log analysis)

## 🚀 Project Roadmap
- [X] Phase 1: php-lab-node (patched reference)
 - [X] Phase 1b: lamp (legacy, unpatched)
- [X] Phase 2: Establish baseline logging & process monitoring
- [ ] Phase 3: Build detection logic (Sigma rule + Python log analyzer)
- [ ] Phase 4: Patch the environment and verify remediation
- [ ] Phase 5: Write an incident-response-style report

*Detailed logs and documentation will be added as each phase is completed.*


## 📖 Step-by-Step Implementation Log

### Phase 1: Lab Environment Setup (`php-lab-node`)

#### 1. Virtual Machine and Base System
- **Host:** VMware Workstation, Ubuntu Server 24.04 LTS (`php-lab-node`)
- **Specs:** 2 vCPUs, 4 GB RAM, 25 GB disk

<img src="images/1_vmware_new_vm_wizard.png" alt="VMware New Virtual Machine Wizard" width="500">

The system was updated and SSH was enabled, following the same process as `k8s-homelab-node`.

```bash
sudo apt update && sudo apt upgrade -y
ip a
sudo ufw allow ssh
sudo ufw enable
```

<img src="images/2_php_lab_node.png" alt="VMware library and terminal after update" width="400">

#### 2. PHP Installation
PHP CLI and PHP-FPM were installed from the Ubuntu repository.

```bash
sudo apt install -y php-cli php-fpm
php -v
```

<img src="images/3_php_version.png" alt="php -v output" width="600">




The reported version (8.3.6) is below the upstream fix version (8.3.36). Since Ubuntu backports security fixes without changing the upstream version number, the package changelog and the Ubuntu CVE tracker were checked before drawing a conclusion.

#### 3. Changelog and CVE Tracker Verification
```bash
apt changelog php8.3-cli 2>/dev/null 
```
<img src="images/4_php_changelog.png" alt="apt changelog output on php-lab-node" width="600">

This retrieves the changelog of the installed package from Ubuntu's servers, listing the security fixes included in that package version. `2>/dev/null` suppresses error messages.

Both Ubuntu CVE tracker entries were checked:
- https://ubuntu.com/security/CVE-2026-109618
- https://ubuntu.com/security/CVE-2026-109619

Both list `8.3.6-0ubuntu0.24.04.13` (noble) as the fixed version.

<img src="images/5_ubuntu_cve_tracker.png" alt="Ubuntu CVE tracker showing the fixed version" width="600">

#### 4. Assessment
- **Patch status:** Not affected
- **Reasoning:** Installed package `8.3.6-0ubuntu0.24.04.13` equals the fixed version listed on the Ubuntu tracker for both CVEs. The changelog shows no pending update, and `apt-cache policy` reports Installed and Candidate as the same version.
- **Verification sources:** `php -v`, `apt changelog`, Ubuntu CVE tracker (CVE-2026-109618 / CVE-2026-109619), `apt-cache policy`.
- **Limitation:** Version-based checks are supplemented by package evidence because Ubuntu backports fixes without changing the upstream version number.

---

### Phase 1b: Legacy Node Assessment (`lamp`)

#### Background
After confirming the patched baseline on `php-lab-node`, I located an older LAMP server (LAMP stands for Linux, Apache, MariaDB, PHP) in my VMware library that I had built previously but had not used for some time. Since the purpose of this lab is to compare patched and unpatched states, this server provides a useful counterpart to the reference node.

<img src="images/6_lamp_vmware_library.png" alt="VMware library with the LAMP VM" width="500">

#### 1. Access and Baseline Preservation
The server was already fully configured, with SSH enabled from the initial build. Unlike `php-lab-node`, it was **not** upgraded at this stage. The aim was to preserve the existing PHP version as an unpatched baseline, so that the vulnerable state could be documented before any remediation.


#### 2. Version Check
```bash
php -v
```

<img src="images/7_lamp_php_version.png" alt="php -v output on lamp" width="600">


The version number alone does not determine patch status, so the changelog was checked as well.

#### 3. Changelog Verification
```bash
apt changelog php8.3-cli 2>/dev/null | head -n 3
apt changelog php8.3-cli 2>/dev/null | grep CVE
```

<img src="images/8_lamp_changelog.png" alt="apt changelog output on lamp: installed version and CVE list (grep CVE)" width="600">

The output shows the installed package (`8.3.6-0ubuntu0.24.04.5`, noble-security) and the full CVE list from the changelog, filtered with `grep CVE`. CVE-2026-109618 and CVE-2026-109619 do not appear.


#### 4. Disable Automatic Updates
To keep the vulnerable state stable during documentation, `unattended-upgrades` was stopped and disabled:

```bash
sudo systemctl stop unattended-upgrades
sudo systemctl disable unattended-upgrades
sudo systemctl status unattended-upgrades --no-pager
sudo nano /etc/apt/apt.conf.d/20auto-upgrades
```

Within `20auto-upgrades`, both periodic settings were set to `"0"`:
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";

Status after change: `inactive (dead)`, `disabled`.



#### 5. Repository Verification
```bash
date
sudo apt update
apt-cache policy php8.3-cli
```

`apt update` refreshes the local package index without installing anything. Before this step, apt's cache could be outdated, so `Candidate` might not show the fix. After the refresh, `apt-cache policy` shows:

- **Installed:** 8.3.6-0ubuntu0.24.04.5
- **Candidate:** 8.3.6-0ubuntu0.24.04.13 (from noble-updates and noble-security)

<img src="images/9_apt_policy_comparison.png" alt="apt-cache policy comparison: lamp (installed .5, candidate .13) vs php-lab-node (installed .13, candidate .13)" width="700">

The same command on `php-lab-node` (Phase 1) shows the fixed version as installed, which gives a direct comparison:

- `lamp`: Installed `8.3.6-0ubuntu0.24.04.5`, Candidate `8.3.6-0ubuntu0.24.04.13`. Affected, update available.
- `php-lab-node`: Installed `8.3.6-0ubuntu0.24.04.13`, Candidate `8.3.6-0ubuntu0.24.04.13`. Patched, no update pending.

The `apt changelog` request for `.13` returned 404 from the changelog server, so the repository and tracker are used as primary evidence instead.


#### 6. Cross-reference with Ubuntu CVE Tracker
Both tracker entries list `8.3.6-0ubuntu0.24.04.13` (noble) as the fixed version:
- https://ubuntu.com/security/CVE-2026-109618
- https://ubuntu.com/security/CVE-2026-109619

The installed package `8.3.6-0ubuntu0.24.04.5` is not listed. The tracker shows only the fixed version per release, so this is expected. The installed version is older than the fixed version, and the repository check in step 5 confirms the update is available.


#### 7. Assessment
- **Patch status:** Affected
- **Reasoning:** Installed `8.3.6-0ubuntu0.24.04.5` is older than the fixed version `8.3.6-0ubuntu0.24.04.13`. Confirmed by changelog, tracker, and repository candidate.
- **Remediation:** Pending. Will be applied and verified in Phase 4 to document the before/after state.





### Phase 2: Baseline Logging with auditd

#### Goal
Confirm that the Linux audit framework (`auditd`) records PHP execution and PHP configuration changes on both nodes. These events are the input for the detection work in Phase 3.

#### Lab architecture
- **Target nodes:** `php-lab-node` (patched) and `lamp` (unpatched). Audit rules run here and generate the events.
- **Analysis host:** Kali Linux desktop. Connects over SSH and analyses the collected logs in Phase 3.
- **Log transfer:** Logs are copied to the analysis host with `scp`. No detection logic runs on the target nodes.

#### 1. Verify PHP Integration

**`php-lab-node`: PHP-FPM**
```bash
readlink -f /usr/bin/php
ls /usr/sbin | grep php-fpm
systemctl list-units --type=service | grep php
```

<img src="images/10_php_integration_php_lab_node.png" alt="PHP-FPM service and binary on php-lab-node" width="600">

Result: `/usr/bin/php` resolves to `/usr/bin/php8.3`, `php-fpm8.3` is present, and `php8.3-fpm.service` is active.

**`lamp`: mod_php (Apache)**
```bash
readlink -f /usr/bin/php
ls /usr/sbin | grep php-fpm
apache2ctl -M | grep -i php
systemctl is-active apache2
ls /etc/apache2/mods-enabled | grep -i php
```

<img src="images/11_php_integration_lamp.png" alt="mod_php loaded in Apache on lamp" width="600">

Result: `/usr/bin/php` resolves to `/usr/bin/php8.3`. No `php-fpm` binary is present. Apache reports `php_module (shared)`, and `php8.3.load` and `php8.3.conf` are enabled. PHP runs inside Apache, so the php-fpm audit rule does not apply to this node.

`apache2ctl` printed an `AH00558` warning (ServerName not set). It does not affect the result.

#### 2. Install and Enable auditd
`auditd` is the Linux kernel audit framework. It records security-relevant events such as program execution and file changes.

```bash
sudo apt install -y auditd audispd-plugins
sudo systemctl enable --now auditd
sudo systemctl status auditd --no-pager
```

<img src="images/12_auditd_status_php_lab_node.png" alt="auditd status on php-lab-node" width="600">

<img src="images/13_auditd_status_lamp.png" alt="auditd status on lamp" width="600">

#### 3. Audit Rules
Rules were written to `/etc/audit/rules.d/php-baseline.rules`. They watch the PHP binary for execution, and the PHP configuration files for writes and attribute changes. Directory watches in auditd are not recursive, so configuration files are referenced individually where possible.


```bash
sudo nano /etc/audit/rules.d/php-baseline.rules
```


`php-lab-node`:
```
-w /usr/bin/php8.3 -p x -k php_exec
-w /usr/sbin/php-fpm8.3 -p x -k php_fpm_exec
-w /etc/php/8.3/cli/php.ini -p wa -k php_config_change
-w /etc/php/8.3/fpm/php.ini -p wa -k php_config_change
-w /etc/php/8.3/fpm/pool.d/ -p wa -k php_fpm_pool_change
```

`lamp`:
```
-w /usr/bin/php8.3 -p x -k php_exec
-w /etc/php/8.3/cli/php.ini -p wa -k php_config_change
-w /etc/php/8.3/apache2/php.ini -p wa -k php_config_change
-w /etc/apache2/mods-enabled/ -p wa -k apache_mod_change
```

Loaded and verified with:
```bash
sudo augenrules --load
sudo auditctl -l
```

The `-w` flag sets the path to watch. `-p x` logs execution of that path, and `-p wa` logs writes and attribute changes. The `-k` flag attaches a key so the events can be found later with `ausearch`.

<img src="images/14_auditd_rules_php_lab_node.png" alt="auditd rules loaded on php-lab-node" width="600">

<img src="images/15_auditd_rules_lamp.png" alt="auditd rules loaded on lamp" width="600">


#### 4. Baseline Event
A harmless PHP CLI command was run to generate a known event, and the audit log was searched by key.

```bash
date
php -r 'echo "baseline check\n";'
sudo ausearch -k php_exec -i --start recent | tail -n 20
```

<img src="images/16_auditd_baseline_php_lab_node.png" alt="auditd baseline event on php-lab-node" width="700">

<img src="images/17_auditd_baseline_lamp.png" alt="auditd baseline event on lamp" width="700">

Timestamp of the test: `Sun Oct 25 2026, 21:37 UTC` on both nodes.

In the output, `key=php_exec` shows which rule matched, and `exe=/usr/bin/php8.3` shows the binary that ran. The `comm=php` field is the process name. The output also contains a `key=(null)` entry from `auditctl -R`, which is the rule loading step and not a PHP event.

#### 5. Result
- **php-lab-node:** audit event recorded for `php_exec` key: **yes** (`exe=/usr/bin/php8.3`, `comm=php`).
- **lamp:** audit event recorded for `php_exec` key: **yes** (`exe=/usr/bin/php8.3`, `comm=php`).
- **Observation:** Both nodes record CLI execution of PHP under the `php_exec` key.

#### 6. Assessment
- **Monitoring status:** Partially effective.
- **Reasoning:** `auditd` records CLI execution of PHP on both nodes, and the configuration watches are loaded. This is enough to build detection logic on in Phase 3.
- **Gap:** Requests served through Apache `mod_php` on `lamp` do not trigger the `php_exec` rule, because the process running the code is Apache, not `/usr/bin/php8.3`. The unpatched node is therefore only partly covered.
- **Next step:** Phase 3 builds detection on the CLI events. The web-request gap is documented here, and a separate test for it is planned in a later phase.
Claude arbeider direkte med kodebasen din


__________________________




### Phase 3: Detection Logic

#### Goal
Turn the raw audit events from Phase 2 into detections I can explain and test. The rules are written in Sigma, the open format for detection rules. A small Python script applies them to copies of the audit logs on my analysis host. No detection runs on the lab nodes.

#### 1. Changes to the audit rules
Phase 2 only showed that PHP was started. It did not show what PHP started, and that is the part that matters if a request leads to a shell. I added a rule that records every `execve` made by the web server user (uid 33, `www-data`).

My first idea was to filter the `execve` rule on `exe=/usr/bin/php8.3`. I changed it before testing. As far as I understand the audit timing, an exe filter on exec is checked after the process has been replaced by the new program, so it would match the child and not PHP. I have not tested that claim, so I filtered on the user instead. The cost is noise, since everything `www-data` runs is logged.

Updated rules for `php-lab-node`:

```
-w /usr/bin/php8.3 -p x -k php_exec
-w /usr/sbin/php-fpm8.3 -p x -k php_fpm_exec
-a always,exit -F arch=b64 -S execve -F uid=33 -k web_user_exec
-w /etc/php/8.3/cli/php.ini -p wa -k php_config_change
-w /etc/php/8.3/fpm/php.ini -p wa -k php_config_change
-w /etc/php/8.3/fpm/pool.d/ -p wa -k php_fpm_pool_change
```

Updated rules for `lamp`:

```
-w /usr/bin/php8.3 -p x -k php_exec
-a always,exit -F arch=b64 -S execve -F uid=33 -k web_user_exec
-w /etc/php/8.3/cli/php.ini -p wa -k php_config_change
-w /etc/php/8.3/apache2/php.ini -p wa -k php_config_change
-w /etc/apache2/mods-enabled/ -p wa -k apache_mod_change
```

Again loaded and verified with:
```bash
sudo augenrules --load
sudo auditctl -l
```

<img src="images/18_auditctl_phase3_php_lab_node.png" alt="auditctl rules on php-lab-node after Phase 3 update" width="600">

<img src="images/19_auditctl_phase3_lamp.png" alt="auditctl rules on lamp after Phase 3 update" width="600">



#### 2. Test events
I ran three harmless commands on each node and recorded the time with `date` first. The first is a plain PHP CLI call as `ubuntu`, which repeats the Phase 2 baseline. The second runs PHP as `www-data` and asks it to start a shell and `id`:

```bash
sudo -u www-data php -r 'system("id");'
```


The output shows `uid=33(www-data)`. This is a standard command and nothing is sent to the node from outside. The point of the test is that `auid` still says `ubuntu` in the audit log, even though the process runs as `www-data`. That field is what identifies the person behind the command in a real investigation.

The third command changes the attributes of `php.ini` without changing its content, so the configuration watch should fire:

```bash
stat -c '%a %n' /etc/php/8.3/cli/php.ini
sudo chmod 644 /etc/php/8.3/cli/php.ini
```

<img src="images/20_phase3_tests_php_lab_node.png" alt="Phase 3 test commands on php-lab-node" width="700">

<img src="images/21_phase3_tests_lamp.png" alt="Phase 3 test commands on lamp" width="700">

No web requests were sent to `lamp` in this phase. The `web_user_exec` rule is meant to cover the mod_php path that `php_exec` misses, but the test above runs PHP from the shell as `www-data`, not through Apache. Testing through a real web request is left for a later phase.



#### 3. Collecting the logs
The audit log is readable only by root, so each node copies it to `/tmp` first. I then pulled the copies to the analysis host with `scp` into `logs/`, which is excluded from the repository.

<img src="images/22_phase3_logs_on_kali.png" alt="Audit log copies on the analysis host" width="600">




#### 4. Detection rules
The detections are three Sigma rules in `detection/sigma/`. `php_cli_exec` matches the `php_exec` watch on the PHP binary and is informational, because it fires on any manual PHP run. `web_user_exec` matches any command started by `www-data` and is rated high, since a shell started by the web user is the pattern I most want to catch. `php_config_change` covers writes and attribute changes to PHP and Apache configuration and is rated medium.

The Sigma files are the source of truth. The analysis script applies the `selection` block of each rule to the audit records. It does not use a full Sigma backend, so I did not convert the rules to another SIEM format. The results below come from my script, not from `sigma-cli`.

#### 5. Analysis script
`analysis/parse_audit.py` reads a log copy, groups the raw records by event ID, and applies each rule to the `SYSCALL` record where the audit key lives. The `--since` flag limits the output to the test window, so the Phase 2 events do not mix in. For `execve` events it also prints the arguments from the `EXECVE` record, which shows the command that was started.

```bash
python3 analysis/parse_audit.py logs/php-lab-node/audit-phase3.log --node php-lab-node --since "<test start, UTC>"
python3 analysis/parse_audit.py logs/lamp/audit-phase3.log --node lamp --since "<test start, UTC>"
```

<img src="images/23_analyzer_php_lab_node.png" alt="Analysis output for php-lab-node" width="700">

<img src="images/24_analyzer_lamp.png" alt="Analysis output for lamp" width="700">

#### 6. Result
- **php-lab-node:** `php_cli_exec` 2 matches, `web_user_exec` 2 matches, `php_config_change` 1 match.
- **lamp:** `php_cli_exec` 2 matches, `web_user_exec` 2 matches, `php_config_change` 1 match.
- **Observation:** On both nodes, the shell started by PHP as `www-data` (`sh -c -- id`) and the `id` process it ran were recorded under `web_user_exec` with `auid` still pointing at the login user (1000, which is `ubuntu` on the node). The PHP process itself was recorded only under `php_exec`, because the watch rule matched first.

#### 7. Assessment
- **Detection status:** Partially effective, with one new control aimed at the Phase 2 gap.
- **Reasoning:** The CLI path is detected on both nodes, and configuration changes are detected. The `web_user_exec` rule is the first thing in this project that could catch a shell started from a web request, and the test shows that it fires for a shell started by `www-data`.
- **Gap:** I have not verified that a real request through Apache on `lamp` produces a `web_user_exec` event. The rule should catch it, because Apache runs as `www-data`, but that is an assumption until it is tested. The rule is also noisy, since every command `www-data` runs is logged.
- **Next step:** A controlled web-path test in a later phase, and a tuning pass on the `web_user_exec` rule once I know what normal `www-data` activity looks like on these hosts.
- **Rule overlap:** `php_exec` and `web_user_exec` both cover the `execve` of the PHP process run as `www-data`, but auditd records only one key per event (the first matching rule). The shell and its child process are the events that matter for detection, and those are recorded under `web_user_exec`. Rule order in the file therefore decides which key a PHP process gets. This is documented here and not treated as a bug.

---

#### Phase 3 files
- `detection/sigma/php_cli_exec.yml`
- `detection/sigma/web_user_exec.yml`
- `detection/sigma/php_config_change.yml`
- `analysis/parse_audit.py`
- `config/audit/php-lab-node.rules` and `config/audit/lamp.rules`
