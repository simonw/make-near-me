cd frontend && npm run build && cd ..
now \
  -e CLIENT_ID=@make-near-me-zeit-client-id \
  -e CLIENT_SECRET=@make-near-me-zeit-client-secret \
  -e COOKIE_SECRET=@make-near-me-cookie-secret \
  -e KEEN_PROJECT_ID=@make-near-me-keen-project-id \
  -e KEEN_WRITE_KEY=@make-near-me-keen-write-key
now alias
