# Deployment Decisions & Architecture

## Overview
Manual cloud deployment of the TaskApp (React + Flask + PostgreSQL) on AWS.

---

## Architecture

```
Browser
  │
  ├──► Nginx EC2 (public subnet) — serves React frontend
  │
  └──► ALB (public subnet) — forwards /api/* calls
            │
            ▼
         Flask EC2 (private subnet) — handles API requests
            │
            ▼
         RDS PostgreSQL (private subnet) — stores data
```

---

## AWS Resources

| Resource | Name | Details |
|---|---|---|
| VPC | taskapp-vpc | CIDR: 10.0.0.0/16 |
| Public Subnet | taskapp-public-subnet | 10.0.32.0/20, eu-north-1a |
| Public Subnet 2 | taskapp-public-subnet-2 | 10.0.96.0/20, eu-north-1b |
| Private Subnet | taskapp-private-subnet | 10.0.48.0/20, eu-north-1a |
| Private Subnet 2 | taskapp-private-subnet2-rds | 10.0.80.0/20, eu-north-1b |
| Internet Gateway | taskapp-igw | Attached to taskapp-vpc |
| NAT Gateway | taskapp-nat | In public subnet, for private EC2 outbound |
| ALB | taskapp-alb | Internet-facing, eu-north-1a + eu-north-1b |
| Flask EC2 | taskapp-flask | Ubuntu 22.04, t3.micro, private subnet |
| Nginx EC2 | taskapp-nginx | Ubuntu 22.04, t3.micro, public subnet |
| RDS | taskapp-db | PostgreSQL, db.t3.micro, private subnet |

---

## Security Groups

### ALB SG (taskapp-alb-sg)
| Direction | Port | Source/Destination |
|---|---|---|
| Inbound | 80 | 0.0.0.0/0 (internet) |
| Outbound | 5000 | taskapp-backend(flaskapp)-sg |

### Nginx SG (taskapp-nginx-sg)
| Direction | Port | Source/Destination |
|---|---|---|
| Inbound | 80 | taskapp-alb-sg |
| Outbound | All | 0.0.0.0/0 |

### Flask SG (taskapp-backend(flaskapp)-sg)
| Direction | Port | Source/Destination |
|---|---|---|
| Inbound | 5000 | taskapp-alb-sg |
| Outbound | 443 | 0.0.0.0/0 |
| Outbound | 5432 | taskapp-database(rds)-sg |

### RDS SG (taskapp-database(rds)-sg)
| Direction | Port | Source/Destination |
|---|---|---|
| Inbound | 5432 | taskapp-backend(flaskapp)-sg |

---

## Key Decisions

### Why private subnet for Flask and RDS?
Flask and RDS are not directly accessible from the internet. Only the ALB can reach Flask, and only Flask can reach RDS. This follows the principle of least privilege.

### Why SSM Session Manager instead of bastion host?
SSM is the industry standard. No open SSH ports, no key management, full audit logs via CloudTrail, and free with VPC endpoints.

### Why NAT Gateway?
Private EC2 instances (Flask) need outbound internet access to install packages (apt-get, pip) and pull code from GitHub. NAT Gateway allows outbound-only internet access without exposing the instance.

> **Cost note:** Delete the NAT Gateway when not actively deploying to avoid charges (~$0.045/hour). Recreate it when needed.

### Why ALB instead of direct access to Flask?
- Decouples the frontend from the backend IP
- Enables future scaling (multiple Flask instances)
- Health checks ensure traffic only goes to healthy instances
- Single entry point for all API traffic

### Why systemd for Flask?
Flask is registered as a systemd service so it automatically starts on EC2 reboot. No manual intervention needed.

---

## Route Tables

| Route Table | Subnet | Routes |
|---|---|---|
| taskapp-public-rt | Public subnets | 0.0.0.0/0 → IGW |
| taskapp-private-rt | Private subnets | 0.0.0.0/0 → NAT Gateway |

---

## Frontend Deployment

1. Update `VITE_API_URL` in `.env` to point to ALB DNS name
2. Run `npm run build` locally
3. Push `dist/` to GitHub
4. SSH into Nginx EC2 and run:
   ```bash
   cd /tmp/taskapp && git pull
   sudo cp -r dist/* /var/www/html/
   sudo systemctl restart nginx
   ```

## Backend Deployment

1. SSH into Flask EC2 via SSM Session Manager
2. Pull latest code:
   ```bash
   cd /home/ubuntu/taskapp && git pull
   sudo systemctl restart flask
   ```

---

## How to Start the Application

> Follow this order every time — RDS must be running before Flask starts.

### 1. Start RDS
- Go to **RDS → Databases → taskapp-db → Actions → Start**
- Wait until status shows **Available** (5-10 minutes)

### 2. Start Flask EC2
- Go to **EC2 → Instances → taskapp-flask → Instance State → Start**
- Flask starts automatically via systemd — no manual action needed
- Verify via SSM: `sudo systemctl status flask`

### 3. Start Nginx EC2
- Go to **EC2 → Instances → taskapp-nginx → Instance State → Start**
- Nginx starts automatically on boot

### 4. Recreate ALB
> The ALB is deleted when shutting down to save costs. You must recreate it every time.

**Step 1 — Create Target Group**
- Go to **EC2 → Target Groups → Create target group**
  - Target type: Instances
  - Name: `taskapp-flask-tg`
  - Protocol: HTTP, Port: 5000
  - VPC: `taskapp-vpc`
  - Health check path: `/api/health`
- Register target: select `taskapp-flask` EC2 → include as pending → Create

**Step 2 — Create Load Balancer**
- Go to **EC2 → Load Balancers → Create → Application Load Balancer**
  - Name: `taskapp-load-balancer`
  - Scheme: Internet-facing
  - VPC: `taskapp-vpc`
  - Subnets: `taskapp-public-subnet` (eu-north-1a) + `taskapp-public-subnet-2` (eu-north-1b)
  - Security group: `taskapp-alb-sg`
  - Listener: HTTP:80 → forward to `taskapp-flask-tg`
- Create and wait for state to show **Active**
- Copy the **DNS name** (e.g. `taskapp-load-balancer-xxxxxxxx.eu-north-1.elb.amazonaws.com`)

**Step 3 — Update ALB outbound rule**
- Go to **EC2 → Security Groups → taskapp-alb-sg → Outbound rules → Edit**
  - Add rule: Custom TCP, Port 5000, Destination: `taskapp-backend(flaskapp)-sg`

**Step 4 — Rebuild and redeploy frontend**
- On your local machine, update `.env`:
  ```
  VITE_API_URL=http://<new-alb-dns-name>/api
  ```
- Build and push:
  ```bash
  npm run build
  git add dist/
  git commit -m "update dist with new ALB URL"
  git push
  ```
- SSH into Nginx EC2 and pull:
  ```bash
  cd /tmp/taskapp && git pull
  sudo cp -r dist/* /var/www/html/
  sudo systemctl restart nginx
  ```

**Step 5 — Verify**
- Go to **EC2 → Target Groups → taskapp-flask-tg → Targets tab**
- Flask EC2 should show **Healthy** (may take 1-2 minutes)
- App is accessible at the Nginx public IP

### 5. Recreate NAT Gateway (only if you need to pull code or install packages on Flask EC2)
- Go to **VPC → NAT Gateways → Create NAT Gateway**
  - Subnet: `taskapp-public-subnet`
  - Connectivity: Public
  - Click **Allocate Elastic IP**
- Go to **VPC → Route Tables → taskapp-private-rt → Routes → Edit**
  - Update `0.0.0.0/0` target to the new NAT Gateway ID
- **Delete when done** to avoid charges (~$0.045/hour)

---

## How to Shut Down (to avoid charges)

> Do this in order to avoid unexpected charges.

1. **Delete ALB** — EC2 → Load Balancers → select → Actions → Delete
2. **Delete Target Group** — EC2 → Target Groups → select → Actions → Delete (optional, free)
3. **Stop Flask EC2** — EC2 → Instances → taskapp-flask → Instance State → Stop
4. **Stop RDS** — RDS → Databases → taskapp-db → Actions → Stop (free for 7 days, auto-restarts after)
5. **Delete NAT Gateway + release Elastic IP** — if one exists
6. **Nginx EC2 can stay running** — t3.micro is very cheap and holds your React build

> **Note:** RDS endpoint never changes on stop/start. Only changes if you delete and recreate the instance.

---

## Environment Variables

### Backend (.env on Flask EC2)
```
DATABASE_URL=postgresql://taskuser:<password>@<rds-endpoint>/taskmanager
PORT=5000
FLASK_ENV=production
SECRET_KEY=<secret>
```

### Frontend (.env local)
```
VITE_API_URL=http://<alb-dns-name>/api
```
