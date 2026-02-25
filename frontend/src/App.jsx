import React, { useState, useMemo } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import Login from './components/Auth/Login';
import Register from './components/Auth/Register';
import ProtectedRoute from './components/Auth/ProtectedRoute';
import Navbar from './components/Layout/Navbar';
import HistorySidebar from './components/History/HistorySidebar';
import ChatInterface from './components/Chat/ChatInterface';
import AdminPortal from './components/Admin/AdminPortal';


// Create React Query client
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 5 * 60 * 1000, // 5 minutes
        },
    },
});

function App() {
    const [darkMode, setDarkMode] = useState(() => {
        const saved = localStorage.getItem('darkMode');
        return saved ? JSON.parse(saved) : false;
    });
    const [historyOpen, setHistoryOpen] = useState(false);
    const [selectedConvId, setSelectedConvId] = useState(null);

    const toggleDarkMode = () => {
        setDarkMode((prev) => {
            const newMode = !prev;
            localStorage.setItem('darkMode', JSON.stringify(newMode));
            return newMode;
        });
    };

    // Create theme based on mode with premium feel
    const theme = useMemo(
        () =>
            createTheme({
                palette: {
                    mode: darkMode ? 'dark' : 'light',
                    primary: {
                        main: '#2563eb', // Modern blue
                    },
                    secondary: {
                        main: '#7c3aed', // Purple
                    },
                    background: {
                        default: darkMode ? '#0f172a' : '#f8fafc',
                        paper: darkMode ? '#1e293b' : '#ffffff',
                    },
                },
                shape: {
                    borderRadius: 12,
                },
                typography: {
                    fontFamily: '"Inter", "Outfit", sans-serif',
                    h6: { fontWeight: 700 },
                    h5: { fontWeight: 800 },
                },
                components: {
                    MuiPaper: {
                        styleOverrides: {
                            root: {
                                backgroundImage: 'none',
                                boxShadow: darkMode
                                    ? '0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3)'
                                    : '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
                            },
                        },
                    },
                },
            }),
        [darkMode]
    );

    return (
        <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={theme}>
                <CssBaseline />
                <Router>
                    <Routes>
                        {/* Public routes */}
                        <Route path="/login" element={<Login />} />
                        <Route path="/register" element={<Register />} />

                        {/* Protected routes */}
                        <Route
                            path="/dashboard"
                            element={
                                <ProtectedRoute>
                                    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
                                        <Navbar
                                            darkMode={darkMode}
                                            toggleDarkMode={toggleDarkMode}
                                            onToggleHistory={() => setHistoryOpen(!historyOpen)}
                                        />
                                        <Box sx={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
                                            <HistorySidebar
                                                open={historyOpen}
                                                onClose={() => setHistoryOpen(false)}
                                                onSelectConversation={(id) => setSelectedConvId(id)}
                                                currentConversationId={selectedConvId}
                                            />
                                            <ChatInterface selectedConversationId={selectedConvId} />
                                        </Box>
                                    </Box>
                                </ProtectedRoute>
                            }
                        />

                        <Route
                            path="/admin"
                            element={
                                <ProtectedRoute adminOnly>
                                    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
                                        <Navbar
                                            darkMode={darkMode}
                                            toggleDarkMode={toggleDarkMode}
                                            onToggleHistory={() => setHistoryOpen(!historyOpen)}
                                        />
                                        <Box sx={{ flex: 1, overflow: 'auto' }}>
                                            <AdminPortal />
                                        </Box>
                                    </Box>
                                </ProtectedRoute>
                            }
                        />

                        {/* Redirect root to dashboard */}
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />

                        {/* 404 */}
                        <Route path="*" element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                </Router>
            </ThemeProvider>
        </QueryClientProvider>
    );
}

export default App;
