module.exports = {
  apps: [{
    name: 'backend-quiz',
    script: 'server.py',
    interpreter: '/home/agents/backend-quiz/venv/bin/python',
    cwd: '/home/agents/backend-quiz',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    }
  }]
};
