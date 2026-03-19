# Post-Upgrade Performance Issue Diagnosis

Your upgrade succeeded technically, but you're experiencing performance degradation. Let's systematically diagnose the issue.

## Immediate Checks

**1. Control plane health:**
```bash
# Check control plane components
kubectl get componentstatuses
kubectl get pods -n kube-system | grep -E "apiserver|etcd|controller|scheduler"

# API server metrics
kubectl get --raw /metrics | grep apiserver_request_duration_seconds
kubectl get --raw /metrics | grep apiserver_current_inflight_requests
```

**2. Resource pressure on nodes:**
```bash
kubectl top nodes
kubectl describe nodes | grep -A 10 "Allocated resources"
kubectl get events -A --field-selector type=Warning | tail -20
```

**3. Workload-level issues:**
```bash
kubectl get pods -A | grep -v Running
kubectl get hpa -A  # Check if HPAs are scaling erratically
kubectl logs -n kube-system -l component=kube-proxy --tail=50
```

## Common 1.29→1.30 Issues

**1. CNI/networking changes:**
GKE 1.30 includes networking stack updates that can affect latency patterns.
```bash
# Check for CNI errors
kubectl logs -n kube-system -l k8s-app=cilium --tail=100  # If using Cilium
kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'
```

**2. kube-proxy mode changes:**
Verify if proxy mode shifted unexpectedly:
```bash
kubectl get configmap kube-proxy-config -n kube-system -o yaml | grep mode
kubectl logs -n kube-system -l k8s-app=kube-proxy | grep -i "proxy mode"
```

**3. API server request routing:**
1.30 has updated request prioritization. Check for throttling:
```bash
kubectl get --raw /metrics | grep apiserver_flowcontrol_rejected_requests_total
kubectl get --raw /metrics | grep apiserver_flowcontrol_current_inqueue_requests
```

## Service-Level Diagnosis

**Check your application pods:**
```bash
# Pod restart patterns since upgrade
kubectl get pods -A -o json | jq -r '.items[] | select(.status.restartCount > 0) | "\(.metadata.namespace)/\(.metadata.name): \(.status.restartCount) restarts"'

# Resource constraints causing throttling
kubectl describe pods -A | grep -A 5 -B 5 "cpu\|memory.*limit"

# Service endpoint health
kubectl get endpoints -A | grep -v ":[0-9]"  # Services with no endpoints
```

**Service mesh considerations (if applicable):**
If using Istio, Linkerd, or similar:
```bash
kubectl get pods -n istio-system  # or your mesh namespace
# Check for mesh proxy CPU/memory spikes
kubectl top pods -n istio-system
```

## Likely Root Causes & Fixes

### 1. Resource contention on new nodes
**Symptom:** Higher baseline CPU/memory usage post-upgrade
**Fix:** Node pools may need more resources due to updated system components
```bash
# Check if you need to scale up
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes NEW_SIZE
```

### 2. DNS resolution delays
**Symptom:** 503s correlate with DNS timeouts
**Fix:** CoreDNS may be under-resourced in 1.30
```bash
kubectl get deployment coredns -n kube-system
kubectl scale deployment coredns --replicas=3 -n kube-system  # Increase if needed
```

### 3. Load balancer / Ingress reconfiguration
**Symptom:** 503s from specific services, not cluster-wide
**Fix:** GKE 1.30 may have triggered LB backend updates
```bash
# Check ingress status
kubectl get ingress -A
kubectl describe ingress YOUR_INGRESS -n YOUR_NAMESPACE

# For GKE ingress, check backend services
gcloud compute backend-services list | grep k8s
```

### 4. API priority and fairness changes
**Symptom:** High API latency across all operations
**Fix:** 1.30 has updated flow control. Check for new throttling:
```bash
kubectl get --raw /debug/api_priority_and_fairness/dump_priority_levels
kubectl get --raw /debug/api_priority_and_fairness/dump_queues
```

## Monitoring Commands

**Set up continuous monitoring while you investigate:**
```bash
# API server latency trend
watch 'kubectl get --raw /metrics | grep apiserver_request_duration_seconds_sum'

# Pod churn rate
watch 'kubectl get pods -A | grep -c -E "ContainerCreating|Terminating|Pending"'

# Service endpoint stability
watch 'kubectl get endpoints -A | wc -l'
```

## Quick Wins to Try

1. **Scale up CoreDNS:** `kubectl scale deployment coredns --replicas=3 -n kube-system`
2. **Increase API server resources** (if you have API server resource limits configured)
3. **Check for stuck webhooks:** `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
4. **Verify ingress controller health:** Scale up nginx-ingress, istio-gateway, or your LB controller

## When to Escalate

Contact GKE support if:
- API server metrics show consistent high latency (>1s p95) after trying above fixes
- Control plane components show restarts or errors
- The issue correlates exactly with the upgrade timestamp and affects multiple applications

Include in your support case:
- Cluster name, zone, upgrade timestamp
- Before/after performance metrics
- Output from the diagnostic commands above

Would you like me to dive deeper into any of these areas based on what you find?