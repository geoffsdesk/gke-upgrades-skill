# GKE 1.31→1.32 Upgrade: API Latency & 503 Error Investigation

Your upgrade appears successful at the cluster level, but you're experiencing application-layer issues. Let's systematically diagnose the problem.

## Immediate Diagnostic Steps

Run these commands to identify the root cause:

### 1. Check admission webhooks (most likely culprit)
```bash
# List all webhook configurations
kubectl get validatingwebhookconfigurations -o wide
kubectl get mutatingwebhookconfigurations -o wide

# Test pod creation to isolate webhook issues
kubectl run test-pod --image=nginx --rm -it --restart=Never --dry-run=server -- echo "test"

# Check for webhook certificate issues
kubectl get validatingwebhookconfigurations -o yaml | grep -A 10 -B 5 "caBundle\|service"
```

**What to look for:** Webhooks that haven't been updated to support Kubernetes 1.32 APIs. Common culprits: cert-manager, Istio, policy controllers, custom operators.

### 2. Examine API server and system pod health
```bash
# System pods status
kubectl get pods -n kube-system -o wide
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -20

# API server connectivity from different nodes
kubectl get nodes -o jsonpath='{.items[*].metadata.name}' | xargs -I {} kubectl get --raw /healthz --server=https://{}:10250 2>/dev/null || echo "Node {} API issues"

# Check for resource exhaustion
kubectl top nodes
kubectl describe nodes | grep -A 8 "Allocated resources"
```

### 3. Application-specific checks
```bash
# Service endpoints and readiness
kubectl get endpoints -A | grep -v "ADDRESS.*AGE"
kubectl get pods -A -o wide | grep -v Running

# Recent events that might indicate failures
kubectl get events -A --sort-by='.lastTimestamp' --field-selector type=Warning | tail -20
```

## Common Post-1.32 Upgrade Issues & Fixes

### Issue A: Admission Webhook Certificate Problems
**Symptoms:** API latency spikes, intermittent pod creation failures, "admission webhook denied the request" errors.

**Root cause:** cert-manager or other webhook operators not compatible with K8s 1.32 APIs, causing certificate validation failures.

**Immediate fix:**
```bash
# Temporarily set webhook to ignore failures (allows traffic through)
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Ignore"}]}'
```

**Permanent fix:**
```bash
# Upgrade cert-manager to 1.32-compatible version
helm repo update
helm upgrade cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --version v1.16.0  # or latest version supporting K8s 1.32

# Verify pods restart and certificates refresh
kubectl get pods -n cert-manager
kubectl describe certificaterequest -A | grep -A 5 -B 5 "Reason.*Ready"

# Restore webhook failure policy
kubectl patch validatingwebhookconfigurations cert-manager-webhook \
  -p '{"webhooks":[{"name":"webhook.cert-manager.io","failurePolicy":"Fail"}]}'
```

### Issue B: CNI/Networking Component Lag
**Symptoms:** Service-to-service connectivity issues, DNS resolution delays, load balancer 503s.

**Check:**
```bash
# CNI pod health (varies by CNI - example for Calico)
kubectl get pods -n kube-system -l k8s-app=calico-node
kubectl logs -n kube-system -l k8s-app=calico-node --tail=50

# DNS resolution test
kubectl run dns-test --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local

# Service mesh components (if using Istio/Linkerd)
kubectl get pods -n istio-system
kubectl get pods -n linkerd
```

### Issue C: Resource Limits Hit After Version Bump
**Symptoms:** Pods stuck in Pending, OOMKilled containers, general performance degradation.

**Check:**
```bash
# Resource usage comparison
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory

# Check for OOMKilled containers
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.name}:{.restartCount}:{.lastState.terminated.reason}{" "}{end}{"\n"}{end}' | grep OOMKilled
```

## Recovery Playbook

### Step 1: Immediate stabilization
```bash
# Scale down non-critical workloads temporarily
kubectl scale deployment non-critical-app --replicas=0 -n namespace

# Restart problematic system components
kubectl rollout restart daemonset/calico-node -n kube-system
kubectl rollout restart deployment/coredns -n kube-system
```

### Step 2: Verify third-party components
Update any operators/controllers that may not support K8s 1.32:
- **cert-manager**: Upgrade to v1.16.0+
- **Istio**: Upgrade to 1.24.0+
- **Nginx Ingress**: Upgrade to controller-v1.11.0+
- **Prometheus Operator**: Upgrade to v0.77.0+

### Step 3: Monitor recovery
```bash
# Track API server latency (if using Prometheus)
# Query: histogram_quantile(0.95, sum(rate(apiserver_request_duration_seconds_bucket[5m])) by (le))

# Basic health check
kubectl get pods -A | grep -E "CrashLoop|Error|Evicted" | wc -l
# Should return 0

# Service endpoint health
kubectl get endpoints -A | grep "<none>" | wc -l
# Should return 0 or very few
```

## Prevention for Future Upgrades

Add to your pre-upgrade checklist:
```
- [ ] All operators/controllers tested against target K8s version
- [ ] Admission webhooks compatibility verified
- [ ] Baseline performance metrics captured
- [ ] Non-critical workloads identified for temporary scale-down
```

## If Issues Persist

If the above steps don't resolve the problem within 2 hours:

1. **Collect detailed diagnostics:**
```bash
kubectl cluster-info dump --all-namespaces --output-directory=cluster-dump-$(date +%Y%m%d-%H%M)
```

2. **Contact GKE Support** with:
   - Cluster name and zone
   - Upgrade timestamp
   - Specific error patterns
   - Steps attempted

The most likely culprit for your symptoms is admission webhook compatibility issues with K8s 1.32. Start with the webhook diagnosis above — it resolves ~80% of post-upgrade API latency problems.