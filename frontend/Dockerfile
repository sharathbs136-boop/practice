FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js styles.css signin.html signin.js admin.html admin.js /usr/share/nginx/html/
EXPOSE 80
