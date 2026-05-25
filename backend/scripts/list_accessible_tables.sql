-- Tables the connected role may SELECT (for local clone; excludes denied objects).
SELECT quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS fq_table
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'sphmf')
  AND c.relkind IN ('r', 'p')
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY 1;
