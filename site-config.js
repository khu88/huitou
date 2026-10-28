'use strict';
// Set repositoryPublished to true after the repository is created and accessible.
window.ConfSite = Object.freeze({
  repositoryUrl: 'https://github.com/khu88/huitou',
  repositoryLabel: 'khu88/huitou',
  repositoryPublished: true,
});

(() => {
  const config = window.ConfSite;
  document.querySelectorAll('[data-repository-link]').forEach(link => {
    link.href = config.repositoryUrl;
    link.title = config.repositoryPublished ? '加入我们的 GitHub 仓库' : '计划仓库地址，尚未创建或公开';
  });
  document.querySelectorAll('[data-repository-address]').forEach(node => {node.textContent = config.repositoryUrl;});
  document.querySelectorAll('[data-repository-status]').forEach(node => {
    node.textContent = config.repositoryPublished ? '欢迎 Star · 反馈 · 共建' : '仓库筹备中';
  });
})();
