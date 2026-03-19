# GKE 1.29 → 1.30 Upgrade Checklists
## Autopilot Clusters: 2 Dev (Rapid) + 2 Prod (Stable)

---

## PRE-UPGRADE CHECKLIST

### Phase 1: Environment Assessment & Planning

#### Cluster Configuration Audit
- [ ] Verify all 4 clusters are in Autopilot mode (not Standard)
  ```bash
  # Run on each cluster
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE | grep "autopilot:"
  ```
- [ ] Confirm current versions:
  - [ ] Dev clusters running 1.29 on Rapid release channel
  - [ ] Prod clusters running 1.29 on Stable release channel
  ```bash
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE | grep -E "currentNodeVersion|currentMasterVersion|releaseChannel"
  ```
- [ ] Document release channel settings (Rapid for dev, Stable for prod must be maintained)
  ```bash
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE --format="value(releaseChannel.channel)"
  ```
- [ ] List all node pools and verify they're Autopilot-managed (no custom node pools)
  ```bash
  gcloud container node-pools list --cluster=CLUSTER_NAME --zone=ZONE
  ```

#### Workload Readiness Assessment
- [ ] **Identify all workloads** across clusters:
  ```bash
  kubectl get all --all-namespaces
  ```
- [ ] **Scan for bare pods** (pods not managed by Deployments, StatefulSets, DaemonSets, Jobs):
  ```bash
  kubectl get pods --all-namespaces --field-selector metadata.ownerReferences=null
  ```
  - [ ] Document any bare pods found
  - [ ] Plan migration or scheduled downtime for bare pods
- [ ] **Verify Pod Disruption Budgets (PDBs)** exist for critical workloads:
  ```bash
  kubectl get pdb --all-namespaces
  ```
  - [ ] Check PDB coverage for stateful apps, databases, message queues
  - [ ] Verify minAvailable/maxUnavailable values are appropriate
  - [ ] For dev clusters: PDBs recommended but not critical
  - [ ] For prod clusters: PDBs required for high-availability workloads
- [ ] **Check graceful shutdown configuration**:
  ```bash
  # Sample check across deployments
  kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.terminationGracePeriodSeconds}{"\n"}{end}'
  ```
  - [ ] Verify terminationGracePeriodSeconds ≥ 30 seconds for critical apps
  - [ ] Review SIGTERM handling in application startup definitions

#### Resource Request Validation (Autopilot-Mandatory)
- [ ] **Audit all Pods for mandatory resource requests**:
  ```bash
  kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[0].resources.requests}{"\n"}{end}'
  ```
- [ ] **Scan for missing resource requests on containers**:
  ```bash
  kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.name}{"\t"}{.resources.requests}{"\n"}{end}' | grep -E "(<nil>|<empty>)"
  ```
  - [ ] Document Pods/Deployments without CPU requests
  - [ ] Document Pods/Deployments without memory requests
  - [ ] Create issue list: Autopilot requires resource requests on ALL workloads
  - [ ] **ACTION**: Update workload manifests with requests before upgrade
- [ ] **Verify resource requests are Autopilot-compatible**:
  - [ ] Min CPU: 10m, Max: unbounded (within node limits)
  - [ ] Min memory: 64Mi, Max: unbounded
  - [ ] No guaranteed QoS pods with extreme reservations

### Phase 2: API Deprecation & Compatibility Checks

#### Kubernetes 1.30 API Deprecations
- [ ] **Check for deprecated beta APIs in use**:
  ```bash
  kubectl api-resources | grep -i beta
  ```
- [ ] **Scan for v1beta1 resource versions** (many graduating to stable in 1.30):
  ```bash
  kubectl get networkpolicies -A -o yaml | grep "apiVersion:"
  kubectl get poddisruptionbudgets -A -o yaml | grep "apiVersion:"
  kubectl get certificatesigningrequests -A -o yaml | grep "apiVersion:"
  ```
- [ ] **Check for removed APIs**:
  - [ ] No usage of `admissionregistration.k8s.io/v1beta1` (removed in 1.30)
  - [ ] No usage of `apiextensions.k8s.io/v1beta1` CRDs (migrate to v1)
  - [ ] No usage of `autoscaling/v2beta2` HPA (use autoscaling/v2)
  ```bash
  # Check HPA versions
  kubectl get hpa -A -o yaml | grep "apiVersion:"
  ```
- [ ] **Audit custom resources and CRDs**:
  ```bash
  kubectl get crd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.group}{"\n"}{end}'
  ```
  - [ ] Verify all CRD definitions have storage version set to v1 (not v1beta1)
  - [ ] Document any external CRDs that may need updates

#### Feature Gate Changes
- [ ] Review Kubernetes 1.30 feature gate changes
- [ ] Check if any disabled-by-default features are required by workloads
- [ ] Verify no custom feature gates in GKE configuration

#### GKE-Specific Deprecations
- [ ] Check GKE release notes for 1.30 for any removed features
- [ ] Verify no dependency on deprecated GKE add-ons (e.g., deprecated monitoring agents)

### Phase 3: Operations Readiness

#### Monitoring & Observability Setup
- [ ] **Verify metrics collection is working**:
  ```bash
  kubectl get pods -n kube-system | grep -E "prometheus|metrics|monitoring"
  ```
- [ ] **Confirm cluster health metrics available**:
  - [ ] GKE Monitoring dashboard accessible
  - [ ] Node CPU, memory utilization visible
  - [ ] Pod resource usage visible
- [ ] **Set up upgrade monitoring alerts** (if using Prometheus/GCP Monitoring):
  - [ ] Alert on control plane unavailability
  - [ ] Alert on node not ready count
  - [ ] Alert on pod eviction rate spike
- [ ] **Document baseline metrics** before upgrade:
  ```bash
  kubectl top nodes
  kubectl top pods --all-namespaces
  ```

#### Backup & Recovery Planning
- [ ] **Backup cluster configurations**:
  ```bash
  # Export cluster config
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE > cluster-backup.yaml

  # Export all resources
  kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
  ```
- [ ] **Backup ConfigMaps and Secrets** (if applicable):
  ```bash
  kubectl get configmap --all-namespaces -o yaml > configmaps-backup.yaml
  kubectl get secret --all-namespaces -o yaml > secrets-backup.yaml
  ```
- [ ] **Document etcd backup procedure** (automated in Autopilot, verify enabled)
- [ ] **Test restore procedure** on non-prod cluster (optional for prod planning)

#### Access & Troubleshooting Preparation
- [ ] **Note**: Autopilot does NOT support node SSH access
  - [ ] Plan to use pod debugging (kubectl exec, kubectl debug) for troubleshooting
- [ ] **Verify kubectl access** to all clusters:
  ```bash
  kubectl cluster-info
  kubectl auth can-i get pods --all-namespaces
  ```
- [ ] **Set up pod debugging** (alpha feature, requires gke-gcloud-auth-plugin):
  ```bash
  kubectl debug node NODE_NAME -it --image=ubuntu
  ```
- [ ] **Prepare troubleshooting contacts** and escalation paths for prod clusters

### Phase 4: Dev Cluster Pre-Upgrade (Rapid Channel)

#### Testing in Non-Prod Environment
- [ ] **Schedule upgrade window** for 1-2 dev clusters first
  - [ ] Notify dev team of upgrade timing
  - [ ] Dev clusters on Rapid channel will upgrade first, ideal for validation
- [ ] **Load test on dev cluster** (optional but recommended):
  - [ ] Run workload spike test (150% normal load)
  - [ ] Monitor resource pressure and scheduling
  - [ ] Verify PDB functionality under load
- [ ] **Test workload failover** (if applicable):
  - [ ] Simulate pod eviction during upgrade
  - [ ] Verify graceful shutdown and rescheduling

### Phase 5: Prod Cluster Pre-Upgrade (Stable Channel)

#### Final Prod Readiness
- [ ] **Schedule auto-upgrade window** during planned maintenance window
  - [ ] Coordinate with on-call team
  - [ ] Plan 2-hour maintenance window minimum
  - [ ] Ensure escalation team is on standby
- [ ] **Review prod workload dependencies**:
  - [ ] Document critical path services
  - [ ] Identify any inter-cluster dependencies
  - [ ] Verify external service dependencies (APIs, databases) are operational
- [ ] **Confirm PDB and disruption policies**:
  - [ ] All critical workloads have PDBs
  - [ ] Pod anti-affinity rules are optimized
  - [ ] No single-replica critical pods
- [ ] **Dry-run drain simulation** (optional but recommended for high-criticality):
  - [ ] Manually cordon non-critical nodes and observe rescheduling
  - [ ] Verify no workloads get stuck pending
  - [ ] Uncordon and verify resumption

---

## POST-UPGRADE CHECKLIST

### Phase 1: Immediate Post-Upgrade Validation (First 15 minutes)

#### Control Plane & Cluster Health
- [ ] **Verify control plane upgrade success**:
  ```bash
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE | grep -E "currentMasterVersion|status"
  ```
- [ ] **Confirm master version is 1.30.x**:
  ```bash
  kubectl version --short | grep Server
  ```
- [ ] **Check cluster status is RUNNING**:
  ```bash
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE --format="value(status)"
  ```
- [ ] **Verify no control plane errors**:
  ```bash
  gcloud container clusters describe CLUSTER_NAME --zone=ZONE --format="value(conditions)"
  ```

#### Node & API Server Availability
- [ ] **Confirm all nodes are Ready**:
  ```bash
  kubectl get nodes -o wide
  ```
  - [ ] All nodes status = Ready
  - [ ] No NotReady or NotReadySchedulingDisabled nodes
- [ ] **Check API server connectivity**:
  ```bash
  kubectl get componentstatuses
  kubectl get nodes --watch &  # Brief watch to confirm consistent heartbeat
  ```
- [ ] **Verify node version progression** (may take 5-10 min for all nodes):
  ```bash
  kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'
  ```

#### Pod & Service Stability
- [ ] **Check for pod evictions or crashes**:
  ```bash
  kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -50
  ```
  - [ ] No excessive FailedScheduling events
  - [ ] No unexpected pod terminations
- [ ] **Verify all system pods are Running**:
  ```bash
  kubectl get pods -n kube-system -o wide
  ```
  - [ ] All coredns pods Running
  - [ ] All kube-proxy pods Running
  - [ ] All GKE system pods Running
- [ ] **Quick service connectivity test**:
  ```bash
  # Run a test pod and verify DNS/service access
  kubectl run -it --rm test-pod --image=busybox --restart=Never -- sh
  # Inside pod: ping kubernetes.default, nslookup kubernetes.default
  ```

### Phase 2: Workload Health Validation (First 30-60 minutes)

#### Application Readiness
- [ ] **Verify all workloads are Running/Ready**:
  ```bash
  kubectl get pods --all-namespaces --field-selector=status.phase!=Running
  kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -v True
  ```
- [ ] **Check for pending pods**:
  ```bash
  kubectl get pods --all-namespaces --field-selector=status.phase=Pending
  ```
  - [ ] Investigate any pods pending > 2 minutes
  - [ ] Check resource availability with `kubectl top nodes`
- [ ] **Verify Deployments/StatefulSets convergence**:
  ```bash
  kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.replicas}{"\t"}{.status.readyReplicas}{"\n"}{end}'
  kubectl get statefulsets --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.replicas}{"\t"}{.status.readyReplicas}{"\n"}{end}'
  ```
  - [ ] All replicas = Ready (no scaling in progress)
  - [ ] No rolling updates stuck in progress

#### Workload Functionality Testing
- [ ] **Test critical application endpoints**:
  - [ ] Dev clusters: smoke test endpoints (HTTP health checks, simple API calls)
  - [ ] Prod clusters: full health check suite (database connectivity, message queue, external APIs)
- [ ] **Verify database connectivity** (if applicable):
  ```bash
  # Example: test database pod health
  kubectl exec -it POD_NAME -- psql -c "SELECT version();"
  ```
- [ ] **Check application logs for errors**:
  ```bash
  kubectl logs -n NAMESPACE DEPLOYMENT_NAME --all-containers=true --tail=100 | grep -i error
  ```
- [ ] **Monitor for memory/CPU spikes**:
  ```bash
  kubectl top pods --all-namespaces --sort-by=memory
  kubectl top pods --all-namespaces --sort-by=cpu
  ```

#### PDB & Disruption Handling Validation
- [ ] **Verify PDBs still present and valid**:
  ```bash
  kubectl get pdb --all-namespaces -o wide
  kubectl get pdb --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.disruptionsAllowed}{"\n"}{end}'
  ```
- [ ] **Confirm no workloads disrupted during upgrade**:
  - [ ] Check pod restart counts haven't increased unexpectedly:
    ```bash
    kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}' | awk '$3 > 5 {print}'
    ```

### Phase 3: API & Feature Validation (30-60 minutes post-upgrade)

#### API Version Compatibility Check
- [ ] **Verify no API deprecation warnings**:
  ```bash
  # Apply a test resource to check for deprecation warnings
  kubectl apply -f - --dry-run=server << EOF
  apiVersion: v1
  kind: Pod
  metadata:
    name: test-api-check
  spec:
    containers:
    - name: test
      image: busybox
  EOF
  ```
- [ ] **Re-run API resource audit**:
  ```bash
  kubectl api-resources
  kubectl get all --all-namespaces | head -20  # Spot-check
  ```
- [ ] **Check CRD storage versions** (if using custom resources):
  ```bash
  kubectl get crd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.names.kind}{"\t"}{.spec.versions[?(@.storage==true)].name}{"\n"}{end}'
  ```

#### Feature Gate Verification
- [ ] **Confirm no feature gate-related errors**:
  ```bash
  kubectl describe node NODE_NAME | grep -i feature
  ```
- [ ] **Verify workloads using new 1.30 features work as expected** (if applicable)

#### Autopilot-Specific Validation
- [ ] **Verify resource requests still enforced**:
  ```bash
  # Try to deploy a pod without resource requests (should fail or warn)
  kubectl apply -f - --dry-run=server << EOF
  apiVersion: v1
  kind: Pod
  metadata:
    name: test-no-requests
  spec:
    containers:
    - name: test
      image: busybox
  EOF
  # Expected: error or warning about missing resource requests
  ```
- [ ] **Confirm no node SSH sessions possible** (Autopilot security model):
  - [ ] Verify node pools still locked to Autopilot
  - [ ] Confirm no custom node pool additions

### Phase 4: Observability & Monitoring Validation

#### Metrics & Alerting Verification
- [ ] **Verify GKE Monitoring metrics are flowing**:
  - [ ] GCP Monitoring dashboard shows current data (< 1 min old)
  - [ ] Node metrics (CPU, memory, disk) available
  - [ ] Pod metrics (CPU, memory) available
  - [ ] Network I/O metrics available
- [ ] **Check alert rules are functioning**:
  ```bash
  # In GCP Monitoring
  # Verify any upgrade-related alerts triggered and resolved
  ```
- [ ] **Confirm custom monitoring working** (Prometheus, Datadog, etc.):
  - [ ] Custom metrics ingestion active
  - [ ] No scrape errors in monitoring agent logs
- [ ] **Review upgrade event log**:
  ```bash
  kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -i upgrade
  ```

#### Logging Validation
- [ ] **Verify application logging is flowing**:
  - [ ] Cloud Logging shows recent pod logs
  - [ ] No excessive log errors or exceptions post-upgrade
  - [ ] Log volume is within expected range
- [ ] **Check kube-system logging**:
  ```bash
  kubectl logs -n kube-system --tail=50 -l component=kubelet | head -20
  ```

### Phase 5: Cluster-Specific Post-Upgrade Procedures

#### Dev Clusters (Rapid Channel)
- [ ] **Immediate post-upgrade validation complete** (follow Phases 1-4)
- [ ] **Run automated test suite** (if applicable):
  - [ ] CI/CD pipeline integration tests pass
  - [ ] Load testing on upgraded cluster completes successfully
- [ ] **Document findings** for prod upgrade validation
- [ ] **Test rollback procedure** (optional):
  - [ ] Verify GKE can rollback to 1.29 if critical issues found
  - [ ] Document any rollback steps for prod team
- [ ] **Mark dev upgrade as successful** in upgrade tracker
- [ ] **Share dev upgrade results** with prod team before prod auto-upgrade

#### Prod Clusters (Stable Channel)
- [ ] **Immediate post-upgrade validation complete** (follow Phases 1-4)
- [ ] **Continuous health monitoring** (2-4 hours minimum):
  - [ ] Monitor error rate dashboard
  - [ ] Monitor latency/response time distribution
  - [ ] Monitor resource utilization trends
  - [ ] Monitor customer-facing logs for exceptions
- [ ] **Execute full test suite** if available:
  - [ ] Smoke tests on critical services
  - [ ] Database integrity checks
  - [ ] Cache coherency checks (if applicable)
- [ ] **Verify SLOs/SLIs are met**:
  - [ ] Availability SLI >= target (typically 99.9% for Stable channel)
  - [ ] Latency P99 within baseline ± 10%
  - [ ] Error rate < baseline + 1%
- [ ] **Escalation team on standby** until 4-hour stability gate passed
- [ ] **Document any incidents and mitigation** during upgrade
- [ ] **Schedule post-upgrade retrospective** (if any issues occurred)

### Phase 6: Cleanup & Post-Upgrade Documentation

#### Resource Cleanup
- [ ] **Remove test pods** created during validation:
  ```bash
  kubectl delete pod test-pod test-api-check test-no-requests --ignore-not-found=true
  ```
- [ ] **Verify no orphaned resources** from upgrade process:
  ```bash
  kubectl get pods --all-namespaces | grep -iE "test|debug|temp"
  ```

#### Documentation & Handoff
- [ ] **Document upgrade completion**:
  - [ ] Record actual upgrade duration (control plane + nodes)
  - [ ] Record any issues encountered and resolutions
  - [ ] Document metric anomalies observed
- [ ] **Update runbook** with any new procedures discovered:
  - [ ] New monitoring gaps
  - [ ] New failure modes
  - [ ] Updated escalation procedures
- [ ] **Archive upgrade logs**:
  ```bash
  gcloud logging read "resource.type=k8s_cluster AND protoPayload.methodName=io.cnrm.container.v1.ClusterManager.UpdateCluster" --limit=100 --format=json > upgrade-logs-1-30.json
  ```
- [ ] **Notify stakeholders** of upgrade success
- [ ] **Schedule post-upgrade review** with ops and dev teams

---

## ENVIRONMENT-SPECIFIC NOTES

### Dev Clusters (Rapid Channel)
- Upgrades automatically ~1-2 weeks after GKE release
- Ideal for validation before prod
- Less stringent SLO requirements allow more aggressive testing
- Use dev upgrade results to refine prod procedures

### Prod Clusters (Stable Channel)
- Manual upgrade window (monthly or quarterly)
- Recommend scheduling during low-traffic periods
- Escalation team and lead engineer required on-call
- 4-hour post-upgrade stability monitoring minimum
- Consider rolling upgrades if business requires zero downtime

### Autopilot-Specific Considerations
- No SSH access to nodes (use kubectl debug for troubleshooting)
- Mandatory resource requests enforced (all containers must have CPU/memory requests)
- Node scaling automatic (no manual node pool management)
- Release channels are mandatory (no custom update scheduling per node)
- Control plane upgrades transparent and unavoidable (no option to defer)
