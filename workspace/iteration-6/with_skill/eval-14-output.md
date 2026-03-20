# Post-Upgrade Issue Analysis: API Latency & 503 Errors

Your upgrade completed successfully at the infrastructure level, but you're experiencing service degradation. Let's diagnose the application and configuration layer issues that commonly emerge after GKE upgrades.

## Immediate Diagnostic Steps

Run these commands to identify the root cause:

### 1. Check API server health and load
```bash
# API server pod status
kubectl get pods -n kube-system -l component=kube-apiserver

# API server metrics (if monitoring is available)
kubectl top pods -n kube-system -l component=kube-apiserver

# Check for API server errors in logs
gcloud logging read 'resource.type="k8s_cluster" AND resource.labels.cluster_name="CLUSTER_NAME" AND resource.labels.location="ZONE" AND log_name="projects/PROJECT_ID/logs/events" AND jsonPayload.reason="FailedMount"' --limit=50 --format=json
```

### 2. Identify pods with issues
```bash
# Pods not fully ready
kubectl get pods -A | grep -v "1/1\|2/2\|3/3" | grep -v Completed

# Recent pod restarts (common after node upgrades)
kubectl get pods -A --sort-by='.status.containerStatuses[0].restartCount' | tail -20

# Pods with high restart counts
kubectl get pods -A -o json | jq -r '.items[] | select(.status.containerStatuses[]?.restartCount > 0) | "\(.metadata.namespace)/\(.metadata.name) - \(.status.containerStatuses[0].restartCount) restarts"'
```

### 3. Check for networking/DNS issues
```bash
# CoreDNS pod health
kubectl get pods -n kube-system -l k8s-app=kube-dns

# DNS resolution test
kubectl run dns-test --image=busybox --restart=Never --rm -it -- nslookup kubernetes.default.svc.cluster.local

# Service connectivity
kubectl get svc -A | grep -v ClusterIP.*none
```

## Common 1.29 → 1.30 Issues

### Pod Security Standard enforcement
**GKE 1.30 enables Pod Security Standards by default.** This is the most likely cause of your issues.

**Diagnose:**
```bash
# Check for pod security violations
kubectl get events -A --field-selector reason=FailedCreate | grep -i security

# Check namespace labels for Pod Security
kubectl get namespaces -o yaml | grep -A 3 "pod-security"
```

**Fix:**
```bash
# Temporarily set to permissive mode for troubleshooting
kubectl label namespace NAMESPACE pod-security.kubernetes.io/enforce=privileged
kubectl label namespace NAMESPACE pod-security.kubernetes.io/warn=privileged
```

### CNI/networking configuration changes
**Diagnose:**
```bash
# Check node network configuration
kubectl get nodes -o wide

# Verify CNI pods
kubectl get pods -n kube-system -l component=kube-proxy
kubectl get daemonset -n kube-system

# Check for network policy issues
kubectl get networkpolicies -A
```

### Resource quota/limits recalculation
**After node refresh, resource calculations may have changed.**

**Diagnose:**
```bash
# Node resource capacity
kubectl describe nodes | grep -A 10 "Allocatable:"

# Pods pending due to resources
kubectl get events -A --field-selector reason=FailedScheduling

# Resource quota usage
kubectl get resourcequota -A
```

## Service-Level Issues

### Readiness/liveness probe failures
**New node images may have different timing characteristics.**

**Diagnose:**
```bash
# Check for probe failures
kubectl get events -A --field-selector reason=Unhealthy

# Pods with probe failures
kubectl describe pod POD_NAME -n NAMESPACE | grep -A 5 "Liveness\|Readiness"
```

**Fix:**
```bash
# Increase probe timeouts temporarily
kubectl patch deployment DEPLOYMENT_NAME -p='{"spec":{"template":{"spec":{"containers":[{"name":"CONTAINER_NAME","readinessProbe":{"timeoutSeconds":10,"periodSeconds":30}}]}}}}'
```

### Load balancer/ingress reconfiguration
**Node IP changes can cause LB backend issues.**

**Diagnose:**
```bash
# Check ingress status
kubectl get ingress -A

# LoadBalancer services
kubectl get svc -A --field-selector spec.type=LoadBalancer

# Ingress controller pods
kubectl get pods -n ingress-nginx  # or your ingress controller namespace
```

### HPA/VPA behavior changes
**Autoscalers may be recalibrating after node changes.**

**Diagnose:**
```bash
# HPA status
kubectl get hpa -A

# Recent scaling events
kubectl get events -A --field-selector reason=ScalingReplicaSet
```

## 1.30-Specific Breaking Changes

Check the [GKE 1.30 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes#gke_1300_1301_1302_1303_1304_1305_and_1306) for:

1. **Deprecated API removal** - though this should have been caught pre-upgrade
2. **Default security posture changes**
3. **Container runtime changes** (containerd updates)
4. **Kubernetes feature gate changes**

**Validate deprecated API usage:**
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Immediate Mitigation Steps

While diagnosing, apply these quick fixes:

### 1. Scale up critical services temporarily
```bash
kubectl scale deployment DEPLOYMENT_NAME --replicas=CURRENT_REPLICAS+2 -n NAMESPACE
```

### 2. Restart pods that may have stale configurations
```bash
kubectl rollout restart deployment DEPLOYMENT_NAME -n NAMESPACE
kubectl rollout restart daemonset DAEMONSET_NAME -n NAMESPACE
```

### 3. Check and restart ingress controller
```bash
kubectl rollout restart deployment -n ingress-nginx  # or your ingress namespace
```

## Monitoring and Validation

**Set up monitoring for the key metrics:**
```bash
# API server request latency
kubectl get --raw /metrics | grep apiserver_request_duration_seconds

# Error rates by service
kubectl get --raw /metrics | grep -E "http_requests_total|grpc_requests_total"
```

**Create a validation script:**
```bash
#!/bin/bash
echo "=== Cluster Health Check ==="
kubectl get nodes | grep -v Ready && echo "Node issues found" || echo "All nodes Ready"
kubectl get pods -A | grep -v "Running\|Completed" | wc -l | sed 's/^/Problematic pods: /'
kubectl get svc -A --field-selector spec.type=LoadBalancer | grep -v EXTERNAL-IP | wc -l | sed 's/^/LoadBalancers without IP: /'
```

## Next Steps

1. **Immediate**: Run the diagnostic commands above to identify which of these issues matches your symptoms
2. **Short-term**: Apply the specific fix for your root cause
3. **Long-term**: Update your pre-upgrade checklist to catch Pod Security Standard changes and include a more comprehensive post-upgrade validation suite

The most likely culprits for your specific symptoms (API latency + 503s after successful infrastructure upgrade) are:
1. Pod Security Standards blocking pod creation/restart
2. Networking/DNS issues from CNI changes
3. Load balancer backend reconfiguration delays

Let me know what the diagnostic commands reveal, and I can provide more targeted troubleshooting steps.