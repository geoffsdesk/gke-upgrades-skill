This sounds like a common issue with Kubernetes 1.30 upgrades. Here's a systematic troubleshooting approach:

## Immediate Checks

**1. Check API Server Health**
```bash
# Check API server pods
kubectl get pods -n kube-system | grep apiserver

# Check API server logs for errors
kubectl logs -n kube-system <apiserver-pod> --tail=100
```

**2. Verify etcd Status**
```bash
# Check etcd pods
kubectl get pods -n kube-system | grep etcd

# Check etcd logs
kubectl logs -n kube-system <etcd-pod> --tail=50
```

## Common 1.30 Upgrade Issues

**1. ValidatingAdmissionPolicy Changes**
Kubernetes 1.30 has stricter validation. Check for:
```bash
# Look for admission controller errors
kubectl get events --all-namespaces | grep -i "admission\|validation"

# Check for failed webhooks
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
```

**2. Feature Gate Changes**
Some features were graduated or deprecated:
```bash
# Check kubelet configuration
kubectl get nodes -o wide
kubectl describe node <node-name> | grep -A 10 "System Info"
```

**3. Network Plugin Compatibility**
```bash
# Check CNI plugin status
kubectl get pods -n kube-system | grep -E "(calico|flannel|weave|cilium)"

# Check for network-related errors
kubectl get pods --all-namespaces | grep -v Running
```

## Service-Specific Debugging

**1. Check Service Endpoints**
```bash
# Verify service endpoints are populated
kubectl get endpoints <service-name> -n <namespace>

# Check service configuration
kubectl describe service <service-name> -n <namespace>
```

**2. Pod Readiness Issues**
```bash
# Check pod status and readiness
kubectl get pods -n <namespace> -o wide

# Check readiness probe failures
kubectl describe pod <pod-name> -n <namespace>
```

**3. Ingress/Load Balancer Issues**
```bash
# Check ingress controller
kubectl get pods -n ingress-nginx  # or your ingress namespace
kubectl logs -n ingress-nginx <ingress-controller-pod>
```

## Resource Constraints

**1. Check Resource Usage**
```bash
# Node resource usage
kubectl top nodes

# Pod resource usage
kubectl top pods --all-namespaces

# Check for resource pressure
kubectl describe nodes | grep -A 5 "Conditions:"
```

**2. Check for OOM Issues**
```bash
# Look for OOM killed pods
kubectl get events --all-namespaces | grep -i "oom\|killed"

# Check system logs (if accessible)
journalctl -u kubelet --since="1 hour ago" | grep -i oom
```

## Performance Tuning for 1.30

**1. API Server Configuration**
If you have control over API server settings:
```yaml
# Increase API server resources if needed
--max-requests-inflight=400  # default: 400
--max-mutating-requests-inflight=200  # default: 200
```

**2. etcd Performance**
```bash
# Check etcd performance metrics
kubectl exec -n kube-system <etcd-pod> -- etcdctl endpoint status
```

## Quick Fixes to Try

**1. Restart Core Components** (if possible in your environment):
```bash
# Delete API server pods to restart them
kubectl delete pod -n kube-system -l component=kube-apiserver

# Restart kubelet on nodes (requires node access)
sudo systemctl restart kubelet
```

**2. Check DNS Resolution**
```bash
# Test cluster DNS
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default
```

**3. Validate Webhooks**
```bash
# Temporarily disable problematic webhooks if identified
kubectl delete validatingwebhookconfigurations <webhook-name>
```

## Monitoring Commands

Run these to get real-time insights:
```bash
# Monitor API server response times
kubectl get --raw /metrics | grep apiserver_request_duration

# Watch pod status changes
kubectl get pods --all-namespaces --watch

# Monitor events in real-time
kubectl get events --all-namespaces --watch
```

Start with checking the API server and etcd logs first, as these are the most common sources of issues after a 1.30 upgrade. The 503 errors typically indicate API server overload or admission webhook failures.

What type of cluster are you running (EKS, GKE, AKS, or self-managed)? This will help narrow down the troubleshooting approach.