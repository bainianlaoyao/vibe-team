export type PermissionLevel = 'read' | 'write' | 'none';

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  children?: FileNode[];
  kind?: string;
  size?: string;
  modified?: string;
  owner?: string;
  content?: string;
}

export const fileTree: FileNode = {
  id: 'root',
  name: 'Root',
  type: 'folder',
  children: [
    {
      id: 'projects',
      name: 'Projects',
      type: 'folder',
      children: [
        {
          id: 'ecommerce',
          name: 'E-commerce Platform',
          type: 'folder',
          children: [
            {
              id: 'src',
              name: 'src',
              type: 'folder',
              children: [
                {
                  id: 'components',
                  name: 'components',
                  type: 'folder',
                  children: [
                    {
                      id: 'auth-form',
                      name: 'AuthForm.tsx',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '4.2 KB',
                      modified: 'Jan 28',
                      owner: 'Claude Opus 4.5',
                      content: `import { useState } from 'react';

interface AuthFormProps {
  mode: 'login' | 'register';
  onSubmit: (data: FormData) => void;
}

export default function AuthForm({ mode, onSubmit }: AuthFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ email, password });
  };

  return (
    <form onSubmit={handleSubmit}>
      <input type="email" value={email} onChange={e => setEmail(e.target.value)} />
      <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      <button type="submit">{mode === 'login' ? 'Sign In' : 'Sign Up'}</button>
    </form>
  );
}`,
                    },
                    {
                      id: 'oauth-buttons',
                      name: 'OAuthButtons.tsx',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '2.1 KB',
                      modified: 'Jan 25',
                      owner: 'Claude Opus 4.5',
                    },
                  ],
                },
                {
                  id: 'pages',
                  name: 'pages',
                  type: 'folder',
                  children: [
                    {
                      id: 'login-page',
                      name: 'Login.tsx',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '3.8 KB',
                      modified: 'Jan 22',
                      owner: 'Claude Opus 4.5',
                    },
                    {
                      id: 'profile-page',
                      name: 'Profile.tsx',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '5.2 KB',
                      modified: 'Jan 26',
                      owner: 'Claude Opus 4.5',
                    },
                  ],
                },
              ],
            },
            {
              id: 'server',
              name: 'server',
              type: 'folder',
              children: [
                {
                  id: 'routes',
                  name: 'routes',
                  type: 'folder',
                  children: [
                    {
                      id: 'auth-routes',
                      name: 'auth.ts',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '6.4 KB',
                      modified: 'Jan 28',
                      owner: 'Gemini Pro 2.0',
                    },
                  ],
                },
                {
                  id: 'oauth',
                  name: 'oauth',
                  type: 'folder',
                  children: [
                    {
                      id: 'google-oauth',
                      name: 'google.ts',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '2.8 KB',
                      modified: 'Jan 25',
                      owner: 'Claude Opus 4.5',
                    },
                    {
                      id: 'github-oauth',
                      name: 'github.ts',
                      type: 'file',
                      kind: 'TypeScript',
                      size: '2.6 KB',
                      modified: 'Jan 25',
                      owner: 'Claude Opus 4.5',
                    },
                  ],
                },
              ],
            },
            {
              id: 'db',
              name: 'db',
              type: 'folder',
              children: [
                {
                  id: 'schema-sql',
                  name: 'schema.sql',
                  type: 'file',
                  kind: 'SQL',
                  size: '3.2 KB',
                  modified: 'Jan 24',
                  owner: 'Codex GPT-4',
                },
              ],
            },
            {
              id: 'readme',
              name: 'README.md',
              type: 'file',
              kind: 'Markdown',
              size: '2.4 KB',
              modified: 'Jan 20',
              owner: 'Team',
              content: `# E-commerce Platform

## Overview
A modern e-commerce platform with authentication, payment processing, and inventory management.

## Getting Started
1. Clone the repository
2. Install dependencies: \`npm install\`
3. Start the dev server: \`npm run dev\`

## Features
- User authentication (email/password + OAuth)
- Product catalog
- Shopping cart
- Checkout flow
- Order management`,
            },
          ],
        },
      ],
    },
    {
      id: 'docs',
      name: 'Documentation',
      type: 'folder',
      children: [
        {
          id: 'product-spec',
          name: 'Product Spec.md',
          type: 'file',
          kind: 'Markdown',
          size: '8.6 KB',
          modified: 'Jan 26',
          owner: 'Team',
          content: `# Product Specification

## Authentication System

### Requirements
- Email/password login
- OAuth support (Google, GitHub)
- Password reset flow
- Session management

### User Stories
1. As a user, I want to sign up with my email
2. As a user, I want to login with Google
3. As a user, I want to reset my password`,
        },
        {
          id: 'auth-flows',
          name: 'Auth Flows.pdf',
          type: 'file',
          kind: 'PDF',
          size: '1.2 MB',
          modified: 'Jan 24',
          owner: 'Team',
        },
        {
          id: 'design-guidelines',
          name: 'Design Guidelines.fig',
          type: 'file',
          kind: 'Figma',
          size: '4.8 MB',
          modified: 'Jan 21',
          owner: 'Team',
        },
      ],
    },
    {
      id: 'assets',
      name: 'Assets',
      type: 'folder',
      children: [
        {
          id: 'images',
          name: 'images',
          type: 'folder',
          children: [
            {
              id: 'logo-png',
              name: 'logo.png',
              type: 'file',
              kind: 'PNG Image',
              size: '24 KB',
              modified: 'Jan 15',
              owner: 'Team',
            },
            {
              id: 'hero-jpg',
              name: 'hero.jpg',
              type: 'file',
              kind: 'JPEG Image',
              size: '156 KB',
              modified: 'Jan 15',
              owner: 'Team',
            },
          ],
        },
        {
          id: 'data',
          name: 'data',
          type: 'folder',
          children: [
            {
              id: 'products-csv',
              name: 'products.csv',
              type: 'file',
              kind: 'CSV',
              size: '42 KB',
              modified: 'Jan 22',
              owner: 'Team',
              content: `id,name,price,category,stock
1,Wireless Mouse,29.99,Electronics,150
2,Mechanical Keyboard,89.99,Electronics,75
3,USB-C Hub,45.99,Accessories,200
4,Monitor Stand,34.99,Accessories,120
5,Webcam HD,59.99,Electronics,90`,
            },
          ],
        },
      ],
    },
  ],
};

export const projectNode = fileTree.children?.find(c => c.id === 'projects')?.children?.[0] || fileTree;

export function findNodeById(root: FileNode, id: string): FileNode | null {
  if (root.id === id) return root;
  if (root.children) {
    for (const child of root.children) {
      const found = findNodeById(child, id);
      if (found) return found;
    }
  }
  return null;
}

export function findPathToId(root: FileNode, id: string, path: FileNode[] = []): FileNode[] | null {
  const currentPath = [...path, root];
  if (root.id === id) return currentPath;
  if (root.children) {
    for (const child of root.children) {
      const found = findPathToId(child, id, currentPath);
      if (found) return found;
    }
  }
  return null;
}
