# GKE Autopilot 1.29 → 1.30 Upgrade Checklists

## Overview

This document provides pre-upgrade and post-upgrade checklists for your Autopilot cluster fleet:
- **Dev (2 clusters):** Rapid release channel (auto-upgrade controlled by you)
- **Prod (2 clusters):** Stable release channel (auto-upgrade scheduled for next month)

Since you're running Autopilot, Google manages node upgrades automatically. Your focus shifts to control plane timing, workload compatibility, and validation. These checklists are organized by environment.

---

## Pre-Upgrade Checklist

### Environment & Compatibility

#### Dev Clusters
- [ ] **Cluster names:** ___________________________
- [ ] **Current master version:** Confirm 1.29 with:
  ```bash
  gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE --format="value(currentMasterVersion)"
  ```
- [ ] **Target version confirmed available in Rapid channel:** Check [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- [ ] **Release channel verified:** Rapid
  ```bash
  gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE --format="value(releaseChannel.channel)"
  ```

#### Prod Clusters
- [ ] **Cluster names:** ___________________________
- [ ] **Current master version:** Confirm 1.29
- [ ] **Target version confirmed available in Stable channel:** 1.30 should be available in Stable (typically 4–6 weeks after Rapid release)
- [ ] **Release channel verified:** Stable
- [ ] **Auto-upgrade scheduled date noted:** _______________
- [ ] **Maintenance window aligns with auto-upgrade window:** Verify your cluster's configured maintenance window covers the auto-upgrade date

### API Deprecation & Compatibility

For both dev and prod:
- [ ] **Check for deprecated API usage** in your cluster:
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```
  If output is non-empty, investigate which controllers/apps are using deprecated APIs.

- [ ] **Review GKE 1.30 release notes** for breaking changes:
  - Check for removed APIs (if upgrading from 1.29, typically minimal)
  - Note changes to default behavior or deprecated features becoming unavailable in 1.31
  - Identify any changes to Autopilot-specific constraints (e.g., resource request validation)

- [ ] **Verify third-party controllers/operators** are compatible with 1.30:
  - List installed operators: `kubectl get operators --all-namespaces` (if using OLM)
  - Check vendor documentation or GitHub repos for 1.30 compatibility
  - Common examples: istio, linkerd, datadog-agent, prometheus-operator, external-dns

- [ ] **Test admission webhooks against target version:**
  ```bash
  kubectl get validatingwebhookconfigurations
  kubectl get mutatingwebhookconfigurations
  ```
  For each webhook, confirm the operator/controller is compatible with 1.30.

### Workload Readiness (Both Environments)

#### Pod Disruption Budgets
- [ ] **PDBs configured for critical workloads:**
  ```bash
  kubectl get pdb --all-namespaces
  ```
  Verify that critical applications (databases, message brokers, service mesh control planes) have PDBs that allow at least one pod to be available during node maintenance.

- [ ] **PDB configuration is not overly restrictive:**
  - Avoid `minAvailable: 100%` (blocks all maintenance)
  - Use `maxUnavailable: 1` or percentage-based settings instead

#### Pod & Workload Health
- [ ] **No bare pods (pods not managed by a controller):**
  ```bash
  kubectl get pods --all-namespaces --field-selector=metadata.ownerReferences=null
  ```
  All pods should be owned by a Deployment, StatefulSet, DaemonSet, or Job. Bare pods won't be rescheduled during node upgrades.

- [ ] **Graceful shutdown configured for long-running workloads:**
  - Check `terminationGracePeriodSeconds` in deployments (default is 30s):
    ```bash
    kubectl get deployments --all-namespaces \
      -o json | jq '.items[] | select(.spec.template.spec.terminationGracePeriodSeconds < 60)'
    ```
  - For workloads that need > 30 seconds to shut down cleanly, increase this value in manifests.

- [ ] **StatefulSet workloads have backups:**
  ```bash
  kubectl get statefulsets --all-namespaces
  ```
  Verify recent backups exist for any data-bearing StatefulSets (databases, data stores). Confirm PersistentVolume reclaim policies are appropriate.

#### Resource Requests (Autopilot-Specific)
- [ ] **All containers have resource requests defined:**
  ```bash
  kubectl get pods --all-namespaces -o json | jq '.items[] | select(.spec.containers[].resources.requests == null)'
  ```
  Autopilot requires CPU and memory requests. If your output shows pods without requests, update their manifests before upgrade.

- [ ] **Resource requests are reasonable:**
  - No requests set to `1000m` or higher without justification
  - Memory requests match actual usage patterns to avoid evictions

### Infrastructure & Configuration (Both Environments)

#### Maintenance Windows
- [ ] **Maintenance window is configured and aligns with your off-peak hours:**
  ```bash
  gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE --format="value(maintenancePolicy)"
  ```

- [ ] **For prod clusters:** Confirm your scheduled maintenance window accommodates the auto-upgrade. If not, adjust it now:
  ```bash
  gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start YYYY-MM-DDTHH:MM:SS \
    --maintenance-window-end YYYY-MM-DDTHH:MM:SS \
    --maintenance-window-recurrence RECURRENCE_RULE
  ```

#### Monitoring & Alerting
- [ ] **Metrics pipeline is active:**
  - Cloud Monitoring or Prometheus is collecting cluster metrics
  - Alert rules for key metrics (API server latency, etcd latency, node readiness) are enabled

- [ ] **Logging is active:**
  - Cloud Logging or external log aggregation is capturing cluster and application logs
  - No recent log pipeline errors

- [ ] **Baseline metrics captured:**
  - Note current error rate, latency (p50, p95, p99), and throughput from your critical services
  - This is your reference for post-upgrade validation

### Communication & Planning

#### Dev Clusters
- [ ] **Upgrade window decided:** When will you test the upgrade on dev? (Recommend doing this before prod auto-upgrade)
- [ ] **Team aware:** Notify dev team that control plane will be unavailable briefly during upgrade
- [ ] **Rollback plan:** If 1.30 causes issues, rollback by downgrading the control plane (Google can assist). Note: workload rollbacks may be more complex if they've adapted to 1.30 APIs.

#### Prod Clusters
- [ ] **Auto-upgrade date communicated to stakeholders:** Ops team, app teams, leadership
- [ ] **Expected downtime window noted:** Control plane will be unavailable for ~5–10 minutes. Nodes will be cordoned and drained sequentially (can take 20–60 minutes depending on workload count and PDB settings).
- [ ] **Escalation path documented:** Who to contact if upgrade goes wrong during the scheduled window
- [ ] **On-call team aware:** Ensure on-call is staffed and available during the maintenance window

---

## Post-Upgrade Checklist

### Cluster Health (Run These Immediately After Upgrade)

#### Version Verification
- [ ] **Control plane upgraded to 1.30:**
  ```bash
  gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE --format="value(currentMasterVersion)"
  ```
  Expected output: `1.30.x-gke.y`

- [ ] **All nodes at or above 1.28 (within 2 minor versions of control plane):**
  ```bash
  gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE \
    --format="table(name, version)"
  ```
  In Autopilot, nodes auto-upgrade. Verify all are at least 1.28 (not 1.27 or older).

#### Node & System Pod Health
- [ ] **All nodes in Ready state:**
  ```bash
  kubectl get nodes
  ```
  All nodes should show `Ready` in the `STATUS` column. Investigate any `NotReady`, `SchedulingDisabled`, or `Unknown` nodes.

- [ ] **System pods are running:**
  ```bash
  kubectl get pods -n kube-system
  ```
  Look for the kube-dns, kube-proxy, and gke-metrics-agent pods. All should be in `Running` state.

- [ ] **No stuck Pod Disruption Budgets:**
  ```bash
  kubectl get pdb --all-namespaces
  ```
  Check the `DISRUPTIONSALLOWED` column. If any show `0` and haven't changed, investigate whether a workload is misconfigured.

#### API Server & Control Plane
- [ ] **API server is responsive:**
  ```bash
  kubectl get nodes
  ```
  If this command times out or fails, the API server may still be stabilizing. Wait 2–3 minutes and retry.

- [ ] **No API deprecation warnings in recent logs:**
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_errors_total
  ```
  Should be minimal or zero. If elevated, check what clients are sending invalid requests.

### Workload Health

#### Deployment & StatefulSet Status
- [ ] **All Deployments at desired replica count:**
  ```bash
  kubectl get deployments --all-namespaces --no-headers | awk '{print $1, $2, $3, $4}' | awk '{if ($2 != $4) print "MISMATCH: " $0}'
  ```
  If any output appears, workloads are still scaling up. Wait 30–60 seconds and recheck.

- [ ] **StatefulSets have all replicas ready:**
  ```bash
  kubectl get statefulsets --all-namespaces
  ```
  `READY` column should match `DESIRED`.

- [ ] **No CrashLoopBackOff or pending pods:**
  ```bash
  kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
  ```
  Any output needs investigation. Common causes:
  - Image pull errors (check credentials)
  - Resource constraints (check `kubectl describe pod POD_NAME`)
  - API compatibility (check pod logs for deprecation errors)

#### Application Health
- [ ] **Service endpoints are healthy:**
  ```bash
  kubectl get endpoints --all-namespaces | grep -v '<none>'
  ```
  Services should have endpoints. If a service shows `<none>`, its pods may not be passing readiness checks.

- [ ] **Ingress/LoadBalancer endpoints are responding:**
  ```bash
  kubectl get ingress --all-namespaces
  kubectl get svc --all-namespaces --field-selector=type=LoadBalancer
  ```
  For each, verify the external IP is assigned and the service is accessible from a client.

- [ ] **Health checks and readiness probes passing:**
  ```bash
  kubectl logs -n NAMESPACE DEPLOYMENT_NAME --tail=50 | grep -i "readiness\|liveness\|health"
  ```
  No repeated failures should appear.

### Observability & Metrics

#### Metrics Pipeline
- [ ] **Metrics are flowing:**
  - Check Cloud Monitoring dashboards or Prometheus UI
  - Verify no large gaps in metric collection around the upgrade window
  - Confirm `kubelet` and `kube-state-metrics` metrics are present

- [ ] **Error rates within baseline:**
  ```bash
  # From Cloud Monitoring or Prometheus, compare current error rates to pre-upgrade baseline
  # Expected: no more than a small spike during upgrade, then return to normal
  ```
  If error rates are elevated 10+ minutes after upgrade, investigate:
  - Check application logs for API errors
  - Run deprecated API check again: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`

- [ ] **Latency within baseline:**
  - API server latency (p50, p95, p99) should return to normal within 5 minutes
  - Application response times should match pre-upgrade baselines

#### Logging Pipeline
- [ ] **Logs are flowing to central aggregation:**
  - Cloud Logging UI shows recent cluster and application logs
  - No backlog or pipeline errors

- [ ] **Key error patterns from logs:**
  - Check for `ContainerCannotRun`, `ImagePullBackOff`, or `CrashLoopBackOff` errors
  - Check for webhook rejections or API validation failures
  - Investigate any surge in `ERROR` or `CRITICAL` log lines

### Data & State

#### Persistent Data
- [ ] **PersistentVolumes still mounted and accessible:**
  ```bash
  kubectl get pvc --all-namespaces
  ```
  All should show `Bound`. If any show `Pending`, investigate.

- [ ] **Database/StatefulSet pods accessing volumes:**
  ```bash
  kubectl exec -it -n NAMESPACE POD_NAME -- ls -la /data  # or your mount point
  ```
  Verify files are present and readable.

#### Backup Status
- [ ] **Recent backups of databases/critical data still exist:**
  - Verify backup job logs show successful runs post-upgrade
  - Spot-check backup integrity if possible

### Post-Upgrade Cleanup & Documentation

#### Dev Clusters Only
- [ ] **Testing completed:** Confirm all dev workloads function correctly on 1.30
- [ ] **Known issues or compatibility notes recorded** for prod team
- [ ] **Any required manifest updates completed and pushed to repo**

#### Prod Clusters
- [ ] **Incident severity:** If any issues occurred during auto-upgrade, was a ticket created?
- [ ] **Upgrade duration recorded:** How long did the upgrade actually take? (Useful for planning future maintenance windows)
- [ ] **Any PDB blocks or node drain delays noted:** Were there workloads that delayed the upgrade?

#### All Clusters
- [ ] **Changelog updated:** Document the upgrade date, version, and any issues encountered
- [ ] **Runbook updated:** If you manually intervened or had to troubleshoot, update your runbook
- [ ] **Team retrospective scheduled (if any issues):** Discuss what went well and what to improve

---

## Quick Reference: Dev to Prod Rollout Sequence

### Recommended Timeline

1. **Week 1: Dev Clusters**
   - Manually upgrade control plane on first dev cluster
   - Run full validation checklist
   - Allow nodes to auto-upgrade (24 hours typically)
   - Re-run post-upgrade checklist

2. **Week 1–2: Dev Cluster 2**
   - Repeat with second dev cluster
   - Validate compatibility across your full workload mix
   - Document any issues or required manifest changes

3. **Week 2–3: Prod Preparation**
   - Apply any manifest fixes discovered in dev
   - Final compatibility review
   - Communicate auto-upgrade timing to stakeholders
   - Confirm maintenance window

4. **Prod Auto-Upgrade Date (Next Month)**
   - Control plane auto-upgrades per your release channel schedule
   - Monitor health continuously
   - Have on-call team available

---

## Rollback Procedure

If the upgrade causes critical issues:

### For Control Plane
- **GKE can downgrade your control plane** back to 1.29 if issues are discovered shortly after upgrade
- Contact Google Cloud support to request a rollback (explain the issue)
- Note: Rollbacks are typically only supported within a few hours of the upgrade

### For Nodes (Autopilot)
- Nodes auto-upgrade and cannot be directly downgraded by you
- If node version causes issues, Google support can rebuild the node pool with the previous version (requires support ticket)

### Application Rollback
- If a workload is incompatible with 1.30, rollback your application manifest to a compatible version
- Example: If an operator broke on 1.30, downgrade the operator Helm chart and re-apply

---

## Troubleshooting During Upgrade

### Upgrade appears stuck
- **Symptom:** Control plane upgrade initiated but hasn't completed after 30 minutes
- **Check:** `gcloud container operations list --filter="name:upgrade" --limit=1`
- **Resolution:** Wait up to 1 hour. GKE typically completes control plane upgrades in 5–15 minutes. If still stuck, contact support.

### Nodes not draining
- **Symptom:** After control plane upgrade, nodes are cordoned but some aren't draining
- **Cause:** Pod Disruption Budget too restrictive or pod not respecting termination grace period
- **Check:** `kubectl describe node NODE_NAME` (look for events) and `kubectl get pdb --all-namespaces`
- **Resolution:** Check if the PDB allows evictions; adjust if needed. Increase `terminationGracePeriodSeconds` if pods are timing out during drain.

### New pod failures post-upgrade
- **Symptom:** Pods are CrashLoopBackOff or failing readiness checks
- **Cause:** Deprecated API usage, resource request missing, or admission webhook rejecting pods
- **Check:**
  ```bash
  kubectl describe pod POD_NAME
  kubectl logs POD_NAME --previous  # check last container log
  kubectl get events --all-namespaces | grep -i error
  ```
- **Resolution:** Fix the manifests (deprecation, resource requests) and reapply

### API calls failing with 410 Gone
- **Symptom:** Applications seeing `410 Gone` errors after upgrade
- **Cause:** Deprecated API removed in 1.30
- **Resolution:** Identify the client (check logs), update the CRD/API version in your manifest, and redeploy

---

## Additional Resources

- [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- [GKE 1.30 Release Notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [Autopilot Maintenance & Upgrades](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview#maintenance)
- [Pod Disruption Budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [gcloud Container Clusters Documentation](https://cloud.google.com/sdk/gcloud/reference/container/clusters)
