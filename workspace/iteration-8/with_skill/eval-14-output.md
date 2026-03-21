# Post-Upgrade Troubleshooting Guide: API Latency & 503 Errors

Your upgrade completed successfully at the infrastructure level, but you're experiencing application-layer issues. Let's diagnose systematically.

## Immediate Diagnostic Steps

### 1. Check API Server Health
```bash
# Control plane component status
kubectl get componentstatuses

# API server metrics (if metrics-server is available)
kubectl top nodes
kubectl get --raw /metrics | grep apiserver_request_duration

# Recent events that might indicate issues
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

### 2. Verify Core System Components
```bash
# kube-system pod health
kubectl get pods -n kube-system -o wide

# Look for any restarting or failing system pods
kubectl get pods -A | grep -E "CrashLoop|Error|Pending"

# Check kube-proxy and CNI health specifically
kubectl get pods -n kube-system -l k8s-app=kube-proxy
kubectl get pods -n kube-system -l k8s-app=gke-metadata-server
```

### 3. Network Connectivity Issues
```bash
# Service endpoints
kubectl get endpoints -A | grep -v "none"

# Ingress status
kubectl get ingress -A

# Load balancer services
kubectl get svc -A --field-selector spec.type=LoadBalancer
```

## Most Likely Culprits (in order of probability)

### 1. **Deprecated API Usage Breaking Applications**

**Diagnosis:**
```bash
# Check for deprecated API warnings in recent events
kubectl get events -A --field-selector reason=DeprecatedAPI

# Look for 403/400 errors from applications trying to use removed APIs
kubectl logs -l app=YOUR_APP_LABEL --tail=100 | grep -i "api\|deprecated\|forbidden"
```

**Common 1.31→1.32 API changes:**
- `flowcontrol.apiserver.k8s.io/v1beta2` → `v1beta3` (FlowSchemas, PriorityLevelConfigurations)
- Some webhook configurations may need updates

### 2. **Admission Webhooks Causing Latency**

**Diagnosis:**
```bash
# List all webhooks
kubectl get validatingwebhookconfigurations -o name
kubectl get mutatingwebhookconfigurations -o name

# Check webhook failure modes and timeouts
kubectl get validatingwebhookconfigurations -o yaml | grep -A 5 -B 5 "failurePolicy\|timeoutSeconds"
```

**Fix:** Look for webhooks with:
- Long `timeoutSeconds` (>10s)
- `failurePolicy: Fail` that might be blocking requests
- Webhook endpoints that are unreachable post-upgrade

### 3. **Resource Limits Hit After Upgrade**

**Diagnosis:**
```bash
# Node resource utilization
kubectl top nodes

# Pod resource usage
kubectl top pods -A --sort-by=cpu
kubectl top pods -A --sort-by=memory

# Check for resource pressure
kubectl describe nodes | grep -A 10 "Conditions:\|Allocated resources:"
```

GKE 1.32 may have different resource reservations for system components.

### 4. **DNS Resolution Issues**

**Diagnosis:**
```bash
# CoreDNS status
kubectl get pods -n kube-system -l k8s-app=kube-dns

# DNS performance test from within cluster
kubectl run dns-test --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default
```

### 5. **Ingress Controller or Load Balancer Issues**

**Diagnosis:**
```bash
# If using ingress-nginx or other ingress controllers
kubectl get pods -n ingress-nginx  # or your ingress namespace
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=100

# GKE Ingress (if using GCE ingress class)
kubectl describe ingress YOUR_INGRESS_NAME
```

## Immediate Mitigation Steps

### 1. **Scale Critical Services**
```bash
# Temporarily increase replicas for services showing 503s
kubectl scale deployment YOUR_SERVICE_NAME --replicas=N

# Check if more replicas resolve the issue
kubectl get pods -l app=YOUR_SERVICE_LABEL -o wide
```

### 2. **Restart Problematic Workloads**
```bash
# Rolling restart to pick up any configuration changes
kubectl rollout restart deployment YOUR_SERVICE_NAME

# Monitor rollout
kubectl rollout status deployment YOUR_SERVICE_NAME
```

### 3. **Disable Problematic Admission Webhooks Temporarily**
```bash
# If you identify a slow webhook, temporarily adjust its failure policy
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK_RULE_NAME","failurePolicy":"Ignore"}]}'
```

## Deep Investigation Commands

### Application-Level Diagnosis
```bash
# Service mesh (if using Istio/Anthos Service Mesh)
kubectl get pods -n istio-system
kubectl logs -n istio-system deployment/istiod --tail=100

# Application logs with timestamp correlation
kubectl logs deployment/YOUR_APP_NAME --since=1h | grep -E "error|503|timeout"

# Check service account tokens (may have changed post-upgrade)
kubectl get serviceaccounts -A
```

### Cluster Autoscaler Impact
```bash
# Check if cluster autoscaler is behaving differently
kubectl get events -A --field-selector source=cluster-autoscaler --since=2h

# Node scaling activity
kubectl get nodes --show-labels | grep -E "Ready|NotReady"
```

## Recovery Steps by Root Cause

### If API Deprecation Issues:
1. Update applications to use supported API versions
2. Check operators/controllers for compatibility with 1.32
3. Review admission controllers for API version requirements

### If Webhook Issues:
1. Update webhook configurations with proper `failurePolicy: Ignore` for non-critical webhooks
2. Increase webhook `timeoutSeconds` if needed
3. Verify webhook endpoints are reachable from new nodes

### If Resource Constraints:
1. Add more nodes to handle increased system overhead
2. Adjust resource requests/limits on applications
3. Consider migrating to larger machine types

### If Load Balancer Issues:
1. Recreate services of type LoadBalancer
2. Check firewall rules haven't changed
3. Verify target port configurations

## Validation After Fixes

```bash
# Monitor error rates
kubectl get events -A --field-selector type=Warning --since=10m

# Application health
curl -I http://YOUR_SERVICE_ENDPOINT/health

# API server responsiveness
time kubectl get nodes >/dev/null
```

## Next Steps

1. **Identify the pattern**: Are 503s from specific services or random?
2. **Check application logs**: Look for upstream connection failures
3. **Monitor resource metrics**: Compare pre/post-upgrade baselines
4. **Contact support**: If system-level components are failing, open a GKE support case with cluster name, zone, and timeline of the issue

The fact that nodes are Ready but applications are struggling suggests this is likely an application-layer compatibility issue rather than infrastructure failure. Focus on deprecated APIs and admission webhook behavior first.