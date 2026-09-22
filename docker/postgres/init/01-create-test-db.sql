SELECT 'CREATE DATABASE word_cloud_test'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'word_cloud_test'
)\gexec
