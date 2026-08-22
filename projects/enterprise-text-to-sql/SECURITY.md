# Security Policy

## Supported versions

目前只维护 `main` 分支上的最新版本。这个项目是安全基础骨架，不应在没有数据库原生权限、身份认证和网络隔离的情况下直接暴露到互联网。

## Reporting a vulnerability

请不要在公开 Issue 中发布可利用的安全问题、凭据、真实 SQL 或真实数据。优先使用 GitHub Security Advisories；如果仓库未启用该功能，请联系维护者并提供：

- 影响范围和可复现步骤
- 受影响的配置、数据库方言和组件版本
- 可能的越权、数据泄露或远程执行影响
- 建议的修复方向（如有）

收到报告后，维护者会确认问题、评估影响，并在修复或缓解措施准备好后发布说明。请对测试数据进行匿名化，不要上传 API Key。

## Deployment baseline

- 使用数据库原生只读账号和最小权限。
- 在网关接入 OIDC/SSO、RBAC、速率限制和审计存储。
- 将租户隔离下沉到数据库 Row-Level Security，AST 改写只作为额外防线。
- 禁止将审计日志直接写入公共日志系统而不做访问控制和保留期管理。