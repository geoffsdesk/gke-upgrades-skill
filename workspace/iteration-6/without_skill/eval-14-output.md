After a Kubernetes upgrade, increased API latency and 503 errors typically indicate resource pressure or configuration issues. Here's how to diagnose and resolve this:

## Immediate Diagnostics

**1. Check API Server Health**
```bash
# Check API server pods status
kubectl get pods -n kube-system | grep apiserver

# Check API server logs for errors
kubectl logs -n kube-system -l component=kube-apiserver --tail=100

# Monitor API server metrics
kubectl top pods -n kube-system | grep apiserver
```

**2. Check Control Plane Resources**
```bash
# Check control plane node resources
kubectl describe nodes | grep -A 5 "Conditions:\|Allocated resources:"

# Check if control plane is resource-constrained
kubectl get events --sort-by='.lastTimestamp' | grep -i "failed\|error"
```

## Common v1.30 Issues & Solutions

**1. Increased Memory Usage**
Kubernetes 1.30 has higher memory requirements. Check if control plane nodes need more resources:

```bash
# Check memory usage on control plane nodes
kubectl top nodes

# If using managed cluster, scale up control plane tier
# For self-managed: increase control plane VM sizes
```

**2. API Priority and Fairness Changes**
v1.30 has stricter API flow control:

```bash
# Check API server flow control
kubectl get --raw /metrics | grep apiserver_flowcontrol

# Check if requests are being throttled
kubectl get events | grep -i "rate\|limit\|throttle"
```

**3. etcd Performance Issues**
```bash
# Check etcd health and performance
kubectl get --raw /healthz/etcd

# Check etcd metrics (if accessible)
kubectl logs -n kube-system -l component=etcd --tail=50
```

## Service-Level Diagnostics

**1. Check Service Endpoints**
```bash
# Verify service endpoints are healthy
kubectl get endpoints <your-service-name>

# Check service pods status
kubectl get pods -l app=<your-app> -o wide

# Check pod readiness probes
kubectl describe pods -l app=<your-app> | grep -A 5 "Readiness\|Liveness"
```

**2. Network Policy Changes**
v1.30 may have stricter network policies:

```bash
# Check network policies
kubectl get networkpolicies --all-namespaces

# Test service connectivity
kubectl run debug-pod --image=busybox --rm -it -- wget -qO- <service-name>:<port>
```

## Quick Fixes

**1. Restart Core Components**
```bash
# Restart API server (if self-managed)
kubectl delete pod -n kube-system -l component=kube-apiserver

# Restart DNS (often helps with 503s)
kubectl rollout restart deployment/coredns -n kube-system

# Restart ingress controller
kubectl rollout restart deployment/<ingress-controller> -n ingress-nginx
```

**2. Scale Resources**
```bash
# Scale up your applications temporarily
kubectl scale deployment <your-app> --replicas=<increased-number>

# Check if more worker nodes are needed
kubectl get nodes
kubectl describe nodes | grep -A 5 "Non-terminated pods"
```

**3. Adjust Resource Requests/Limits**
Review and potentially increase resource requests for your services:

```yaml
# Update deployment with higher resources
resources:
  requests:
    memory: "256Mi"  # Increase from previous values
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

## Monitoring Commands

Run these to monitor the situation:

```bash
# Monitor API response times
kubectl get --raw /metrics | grep apiserver_request_duration

# Watch for 503 errors
kubectl logs -f deployment/<your-app> | grep "503\|error"

# Monitor cluster resource usage
watch kubectl top nodes
```

## If Issues Persist

1. **Check release notes** for breaking changes in 1.30
2. **Review addon compatibility** - ensure ingress controllers, CNI, etc. support 1.30
3. **Consider temporary rollback** if business critical
4. **Scale up control plane** resources (CPU/memory)
5. **Check cloud provider status** for any ongoing issues

The most common culprit is increased resource requirements in 1.30. Start with scaling up control plane resources and restarting core components.

What type of cluster are you running (EKS, GKE, AKS, self-managed) and what's your current control plane resource allocation?