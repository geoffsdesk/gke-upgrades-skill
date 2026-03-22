To achieve maximum control over your upgrade timing without sacrificing security, you should rely on GKE's **automated release channels paired with targeted maintenance windows and exclusions**. 

Many teams in strictly regulated environments assume they need to disable auto-upgrades entirely (the legacy "No channel" approach) to get this level of control. However, GKE's release channel exclusions actually offer a much safer and more granular mechanism.

Here is the recommended configuration for your environment:

### 1. The Strategy: "Patch automatically, upgrade minors/nodes intentionally"

The ideal setup for a strict-change-window environment uses a combination of three GKE features:

1. **Release Channel (Stable or Regular):** Ensures you receive fully tested, SLA-backed versions and patches. 
2. **Recurring Maintenance Windows:** Restricts *any* automated action to your approved change control windows (e.g., Saturday 1:00 AM - 5:00 AM).
3. **The `"No minor or node upgrades"` Maintenance Exclusion:** This is the most critical piece for your requirement. It blocks all disruptive minor version upgrades and node pool upgrades, but **allows control plane security patches** to roll out automatically during your maintenance window.

### 2. How this works in practice
* **Security Patches:** When a CVE is patched, GKE updates your control plane automatically, but *only* during your weekend maintenance window. Your nodes are untouched, meaning workloads experience zero disruption.
* **Minor Upgrades & Node Updates:** Your cluster stays locked to its current minor version (and nodes stay locked to their version) until you are ready. When your team plans a maintenance event, you simply execute a user-initiated manual upgrade, which overrides the exclusion.
* **End of Support (EoS):** You can set this exclusion to automatically track the version's End of Support date, ensuring you stay compliant without having to constantly renew the exclusion.

---

### 3. Implementation Runbook

Here are the exact commands to implement this configuration on an existing cluster.

#### Step 1: Ensure you are on a Release Channel
For a financial services production environment, the **Stable** channel is highly recommended.
```bash
# Verify current channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# If not on a channel, enroll in Stable
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

#### Step 2: Define your Approved Change Window
Configure a recurring maintenance window. GKE will restrict all automated patch rollouts to this specific time block. *(Note: Manual upgrades initiated by your engineers will bypass this window).*

```bash
# Example: Upgrades only allowed Saturday starting at 1:00 AM UTC for 4 hours
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T01:00:00Z" \
    --maintenance-window-duration "4h" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

#### Step 3: Apply the Persistent Exclusion
Add the maintenance exclusion that blocks minor and node upgrades but allows control plane patches. By using the `--add-maintenance-exclusion-until-end-of-support` flag, the exclusion will automatically track your current version's EoS date and renew itself when you eventually upgrade.

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "hold-minor-and-nodes" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

#### Step 4: (Optional) Set Disruption Intervals
To ensure GKE doesn't apply patches too frequently (even during your window), you can enforce a "cool-down" period between control plane patches.

```bash
# Require at least 14 days between control plane patch upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval 14d
```

### 4. Operational Workflow for this Configuration

Once configured, your day-to-day operational model becomes highly predictable:

1. **Steady State:** Control plane receives security patches automatically, but strictly during your weekend change window. Workloads are untouched.
2. **Advance Notice:** You can opt-in to Scheduled Upgrade Notifications (via Cloud Logging) to receive a 72-hour advance alert before GKE applies a patch during your window.
3. **Executing a Minor Upgrade:** When your team has planned a major release and tested the next K8s minor version in staging, an engineer runs the manual `gcloud container clusters upgrade` command. Manual upgrades bypass the maintenance windows and exclusions, allowing you to execute the change precisely when your engineers are on bridges. Once the upgrade completes, the `until-end-of-support` exclusion automatically attaches itself to the *new* version.