# Post-Upgrade API Latency & 503 Investigation

Your upgrade completed successfully at the infrastructure level, but you're experiencing application-layer issues. Let's systematically diagnose the root cause.

## Immediate Diagnostics

Run these commands to identify the issue:

### 1. Check API server health and load
```bash
# API server pod status
kubectl get pods -n kube-system -l component=kube-apiserver

# API server metrics (if available)
kubectl get --raw /metrics | grep -E "apiserver_request_duration|apiserver_request_total|etcd_request_duration"

# Check for API server throttling
kubectl get events -A --field-selector reason=TooManyRequests
```

### 2. Examine workload health post-upgrade
```bash
# Pods with issues
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Recent events (last 30 minutes)
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Service endpoints
kubectl get endpoints -A | grep -v ":<none>"
```

### 3. Check for resource pressure
```bash
# Node resource utilization
kubectl top nodes

# Pods consuming high CPU/memory
kubectl top pods -A --sort-by=cpu | head -20
kubectl top pods -A --sort-by=memory | head -20
```

## Common Post-1.32 Upgrade Issues

### 1. **Pod Security Standards enforcement**
GKE 1.32 may have stricter Pod Security Standards. Check for rejected pods:

```bash
# Look for security policy violations
kubectl get events -A --field-selector reason=FailedCreate | grep -i security

# Check pod security context issues
kubectl describe pods -A | grep -A 10 -B 5 "SecurityContext"
```

**Fix:** Update pod security contexts or add security context constraints.

### 2. **Ingress controller compatibility**
Popular ingress controllers (nginx, istio, traefik) sometimes have compatibility issues with new K8s versions:

```bash
# Check ingress controller pods
kubectl get pods -n ingress-nginx -o wide  # or your ingress namespace
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=100

# Verify ingress resources
kubectl get ingress -A
kubectl describe ingress INGRESS_NAME -n NAMESPACE
```

**Fix:** Upgrade ingress controller to a version compatible with K8s 1.32.

### 3. **Service mesh/CNI issues**
Network-related components may need updates:

```bash
# Check CNI/network plugin pods
kubectl get pods -n kube-system | grep -E "gke-|cilium|calico|flannel"

# Istio/service mesh pods (if applicable)
kubectl get pods -n istio-system

# DNS resolution test
kubectl run debug-pod --image=busybox --rm -it -- nslookup kubernetes.default.svc.cluster.local
```

### 4. **Admission webhook failures**
Webhooks might reject requests on the new K8s version:

```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Recent webhook failures
kubectl get events -A | grep -i webhook

# Test webhook endpoints
kubectl get validatingwebhookconfigurations -o yaml | grep -A 5 -B 5 "service:"
```

**Fix:** Update or temporarily disable incompatible webhooks.

### 5. **Deprecated API usage**
Applications may be using APIs that changed behavior in 1.32:

```bash
# Check for deprecated API calls
kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis

# Audit logs (if enabled)
# Check Cloud Logging for "deprecated" API usage
```

## Performance-Specific Checks

### API Server Performance
```bash
# Check API server resource usage
kubectl top pods -n kube-system | grep kube-apiserver

# etcd performance (managed by GKE, but metrics may be available)
kubectl get --raw /metrics | grep etcd_request_duration_seconds
```

### Application Performance
```bash
# Service response times
kubectl get events -A --field-selector reason=Unhealthy

# HPA behavior (if using horizontal pod autoscaler)
kubectl get hpa -A
kubectl describe hpa HPA_NAME -n NAMESPACE
```

## Quick Fixes to Try

### 1. **Restart ingress controllers**
```bash
kubectl rollout restart deployment/ingress-nginx-controller -n ingress-nginx
# Or your specific ingress controller
```

### 2. **Clear DNS cache**
```bash
kubectl rollout restart deployment/coredns -n kube-system
```

### 3. **Restart problem services**
```bash
# Identify and restart services showing 503s
kubectl rollout restart deployment/YOUR_SERVICE -n NAMESPACE
```

## Rollback Consideration

If the issues persist and are severe, consider a temporary rollback:

```bash
# Create new node pool at 1.31 (control plane stays at 1.32)
gcloud container node-pools create nodepool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.XX-gke.XXXX \
  --num-nodes 3 \
  --machine-type e2-standard-4

# Cordon 1.32 nodes and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME
```

**Note:** The control plane will remain at 1.32 (downgrade requires GKE support), but running workloads on 1.31 nodes may resolve application compatibility issues.

## Most Likely Culprits (in order)

1. **Ingress controller incompatibility** — upgrade your ingress controller first
2. **Admission webhook rejecting requests** — check webhook logs and compatibility
3. **Service mesh component issues** — restart/upgrade service mesh components
4. **Application-level API compatibility** — deprecated API usage or client library issues

## Monitoring Commands

While investigating, monitor these continuously:
```bash
# In separate terminals
watch 'kubectl get pods -A | grep -v Running | grep -v Completed'
watch 'kubectl top nodes'
kubectl get events -A -w | grep -E "Warning|Error"
```

What specific services are showing 503 errors? Are they behind an ingress controller or load balancer? This will help narrow down whether it's an infrastructure, networking, or application-level issue.