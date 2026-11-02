FROM nginx:1.27-alpine

# Copy pre-built dist folder: run npm run build with VITE_API_URL set first
COPY dist /usr/share/nginx/html

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
