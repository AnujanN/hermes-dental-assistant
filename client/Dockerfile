FROM node:18-alpine

WORKDIR /app

# Copy package definition
COPY package.json .

# Install Node modules
RUN npm install

# Copy the rest of the application
COPY . .

# Expose Vite dev port
EXPOSE 5173

# Run Vite dev server bound to all network interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
