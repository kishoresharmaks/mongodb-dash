import React, { useState, useEffect, useRef } from 'react';
import {
    Box,
    Paper,
    Typography,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    IconButton,
    Slide,
    Tooltip,
    Tabs,
    Tab,
    Chip,
    FormControl,
    InputLabel,
    Select,
    MenuItem
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TableChartIcon from '@mui/icons-material/TableChart';
import BarChartIcon from '@mui/icons-material/BarChart';
import SecurityIcon from '@mui/icons-material/Security';
import ChatIcon from '@mui/icons-material/Chat';
import SearchIcon from '@mui/icons-material/Search';
import PieChartIcon from '@mui/icons-material/PieChart';
import ShieldIcon from '@mui/icons-material/Shield';
import MovieIcon from '@mui/icons-material/Movie';
import { v4 as uuidv4 } from 'uuid';
import { usePlanMutation, useExecuteConfirmedMutation, useConversation } from '../../hooks/useQuery';
import MessageBubble from './MessageBubble';
import InputBox from './InputBox';
import ResultTable from '../Results/ResultTable';
import VisualizationComponent from '../Results/VisualizationComponent';
import api from '../../services/api';
import demoTemplates from '../../data/demoTemplates';

const Transition = React.forwardRef(function Transition(props, ref) {
    return <Slide direction="up" ref={ref} {...props} />;
});

// Section icon map for demo template categories
const sectionIcon = (section) => {
    if (section.includes('Overview')) return <MovieIcon fontSize="small" />;
    if (section.includes('Query')) return <SearchIcon fontSize="small" />;
    if (section.includes('Visual')) return <PieChartIcon fontSize="small" />;
    if (section.includes('Security') || section.includes('RBAC')) return <ShieldIcon fontSize="small" />;
    return <ChatIcon fontSize="small" />;
};

const sectionColor = (section) => {
    if (section.includes('Overview')) return { bg: 'rgba(99,102,241,0.1)', color: '#6366f1', border: 'rgba(99,102,241,0.3)' };
    if (section.includes('Query')) return { bg: 'rgba(16,185,129,0.1)', color: '#059669', border: 'rgba(16,185,129,0.3)' };
    if (section.includes('Visual')) return { bg: 'rgba(249,115,22,0.1)', color: '#ea580c', border: 'rgba(249,115,22,0.3)' };
    if (section.includes('Security') || section.includes('RBAC')) return { bg: 'rgba(239,68,68,0.1)', color: '#dc2626', border: 'rgba(239,68,68,0.3)' };
    return { bg: 'rgba(37,99,235,0.08)', color: '#2563eb', border: 'rgba(37,99,235,0.2)' };
};

const ChatInterface = ({ selectedConversationId }) => {
    const [messages, setMessages] = useState([]);
    const [conversationId, setConversationId] = useState(null);
    const [currentResults, setCurrentResults] = useState(null);
    const [activeVisualization, setActiveVisualization] = useState(null);
    const [isResultsOpen, setIsResultsOpen] = useState(false);
    const [activeTab, setActiveTab] = useState(0); // 0 for Table, 1 for Chart
    const [pendingPlan, setPendingPlan] = useState(null);
    const [debugMode, setDebugMode] = useState('llm'); // Changed default to 'llm' for real data experience
    const [selectedXAxis, setSelectedXAxis] = useState('');
    const [selectedYAxis, setSelectedYAxis] = useState('');
    const messagesEndRef = useRef(null);
    const [permissions, setPermissions] = useState(null);

    // Fetch latest user data to get fresh permissions
    useEffect(() => {
        const fetchUser = async () => {
            try {
                const res = await api.get('/auth/me');
                if (res.data.success) {
                    setPermissions(res.data.data.user.permissions);
                    // Update localStorage for consistency
                    localStorage.setItem('user', JSON.stringify(res.data.data.user));
                }
            } catch (err) {
                // Fallback to localStorage if API fails
                const user = JSON.parse(localStorage.getItem('user') || '{}');
                setPermissions(user.permissions);
            }
        };
        fetchUser();
    }, []);

    const allowedCollections = permissions?.collections || [];

    const planMutation = usePlanMutation();
    const executeMutation = useExecuteConfirmedMutation();
    const { data: conversationData, isLoading: isLoadingConv } = useConversation(selectedConversationId);

    // Load history when selectedConversationId changes
    useEffect(() => {
        if (conversationData?.queries) {
            const historyMessages = conversationData.queries.map(q => ([
                {
                    id: uuidv4() + '_user',
                    query: q.naturalQuery,
                    isUser: true,
                    timestamp: q.timestamp
                },
                {
                    id: uuidv4() + '_assistant',
                    query: q.naturalQuery,
                    mql: q.generatedMQL,
                    explanation: q.errorMessage ? `Error: ${q.errorMessage}` : `Found ${q.results.count} results.`,
                    resultCount: q.results.count,
                    isUser: false,
                    timestamp: q.timestamp,
                    error: !q.success,
                    visualization: q.metadata?.visualization
                }
            ])).flat();

            setMessages(historyMessages);
            setConversationId(selectedConversationId);

            // Set the latest results if available
            const latestWithResults = [...conversationData.queries].reverse().find(q => q.results.sample?.length > 0);
            if (latestWithResults) {
                // Note: The history only stores samples. Real app would refetch.
                // For now, we'll just show the sample or null.
                setCurrentResults(null);
            }
        }
    }, [conversationData, selectedConversationId]);

    // Auto-scroll to bottom
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // Initialize conversation ID if not set
    useEffect(() => {
        if (!conversationId) {
            setConversationId(uuidv4());
        }
    }, [conversationId]);

    // Handler for demo template clicks — injects a pre-built answer without API call
    const handleDemoTemplate = (template) => {
        const { query, prebuiltResponse } = template;

        // Add the user message
        const userMessage = {
            id: uuidv4(),
            query,
            isUser: true,
            timestamp: new Date()
        };

        // Build the AI response from the prebuilt data
        const assistantMessage = {
            id: uuidv4(),
            query,
            mql: prebuiltResponse.mql_query || null,
            explanation: prebuiltResponse.explanation,
            needsConfirmation: prebuiltResponse.needs_confirmation || false,
            type: prebuiltResponse.type,
            visualization: prebuiltResponse.type === 'visualization' ? {
                chart_type: prebuiltResponse.chart_type,
                title: prebuiltResponse.title,
                x_key: prebuiltResponse.x_key || 'label',
                y_key: prebuiltResponse.y_key || 'value'
            } : null,
            isUser: false,
            timestamp: new Date(),
            error: !prebuiltResponse.success,
            isDemo: true // flag to style/differentiate demo responses
        };

        setMessages((prev) => [...prev, userMessage, assistantMessage]);

        // If it needs confirmation, set pending plan so confirm button works
        if (prebuiltResponse.needs_confirmation && prebuiltResponse.mql_query) {
            setPendingPlan(assistantMessage);
        }
    };

    const handleSendQuery = async (query, vizOptions = {}) => {
        // Add user message
        const userMessage = {
            id: uuidv4(),
            query,
            isUser: true,
            timestamp: new Date()
        };
        setMessages((prev) => [...prev, userMessage]);

        try {
            // Step 1: Get Plan (include visualization preferences)
            const result = await planMutation.mutateAsync({
                query,
                conversationId,
                visualizationPreference: vizOptions.visualize ? {
                    enabled: true,
                    chartType: vizOptions.chartType,
                    debugMode: vizOptions.debugMode || 'auto' // NEW: Pass debug mode
                } : {
                    enabled: false,
                    debugMode: vizOptions.debugMode || 'auto' // Also pass for data-only queries
                }
            });

            if (result.success) {
                const assistantMessage = {
                    id: uuidv4(),
                    query: result.data.query,
                    mql: result.data.mql,
                    explanation: result.data.explanation,
                    needsConfirmation: result.data.needsConfirmation,
                    type: result.data.type,
                    visualization: result.data.visualization,
                    isUser: false,
                    timestamp: new Date()
                };
                setMessages((prev) => [...prev, assistantMessage]);

                if (result.data.needsConfirmation) {
                    setPendingPlan(assistantMessage);
                }
            } else {
                const errorMessage = {
                    id: uuidv4(),
                    explanation: result.message || 'An error occurred',
                    isUser: false,
                    timestamp: new Date(),
                    error: true
                };
                setMessages((prev) => [...prev, errorMessage]);
            }
        } catch (error) {
            const errorMessage = {
                id: uuidv4(),
                explanation: error.message || 'Failed to generate plan',
                isUser: false,
                timestamp: new Date(),
                error: true
            };
            setMessages((prev) => [...prev, errorMessage]);
        }
    };

    const handleConfirmQuery = async () => {
        if (!pendingPlan) return;

        const originalMql = pendingPlan.mql;
        const originalQuery = pendingPlan.query;
        const visualizationConfig = pendingPlan.visualization;

        // Remove confirmation UI from last message
        setMessages(prev => prev.map((msg, idx) =>
            idx === prev.length - 1 ? { ...msg, needsConfirmation: false, isExecuting: true } : msg
        ));

        try {
            const result = await executeMutation.mutateAsync({
                mql: originalMql,
                naturalQuery: originalQuery,
                conversationId,
                metadata: {
                    visualization: visualizationConfig
                }
            });

            if (result.success) {
                // Update the last message with results meta
                setMessages(prev => prev.map((msg, idx) =>
                    idx === prev.length - 1 ? {
                        ...msg,
                        isExecuting: false,
                        resultCount: result.data.resultCount,
                        explanation: `Query confirmed. ${result.data.explanation}`,
                        results: result.data.results
                    } : msg
                ));

                if (result.data.results && result.data.results.length > 0) {
                    setCurrentResults(result.data.results);
                    setActiveVisualization(visualizationConfig);
                    setSelectedXAxis('');
                    setSelectedYAxis('');
                    // If it's a visualization, default to the chart tab
                    if (visualizationConfig) {
                        setActiveTab(1);
                    } else {
                        setActiveTab(0);
                    }
                    setIsResultsOpen(true);
                }
            }
        } catch (error) {
            setMessages(prev => prev.map((msg, idx) =>
                idx === prev.length - 1 ? {
                    ...msg,
                    isExecuting: false,
                    error: true,
                    explanation: `Execution failed: ${error.message}`
                } : msg
            ));
        } finally {
            setPendingPlan(null);
        }
    };

    const handleCancelQuery = () => {
        setMessages(prev => prev.map((msg, idx) =>
            idx === prev.length - 1 ? { ...msg, needsConfirmation: false, explanation: 'Query cancelled by user.' } : msg
        ));
        setPendingPlan(null);
    };

    const handleTabChange = (event, newValue) => {
        setActiveTab(newValue);
    };

    // Group demo templates by section for display
    const templateSections = demoTemplates.reduce((acc, t) => {
        if (!acc[t.section]) acc[t.section] = [];
        acc[t.section].push(t);
        return acc;
    }, {});

    const axisColumns = currentResults && currentResults.length > 0
        ? [...new Set(currentResults.flatMap((r) => (r && typeof r === 'object' ? Object.keys(r) : [])))]
        : [];
    const xAxisOptions = axisColumns;
    const yAxisOptions = axisColumns.filter((key) =>
        currentResults?.some((row) => Number.isFinite(Number(row?.[key])))
    );

    return (
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {/* Messages area */}
            <Box
                sx={{
                    flex: 1,
                    overflowY: 'auto',
                    p: 2,
                    backgroundColor: 'background.default'
                }}
            >
                {messages.length === 0 ? (
                    <Box
                        sx={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            minHeight: '100%',
                            textAlign: 'center',
                            p: 3
                        }}
                    >
                        <Box
                            sx={{
                                width: 80,
                                height: 80,
                                borderRadius: 4,
                                backgroundColor: 'primary.main',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                mb: 3,
                                boxShadow: '0 20px 25px -5px rgba(37, 99, 235, 0.4)'
                            }}
                        >
                            <ChatIcon sx={{ fontSize: 40, color: '#fff' }} />
                        </Box>
                        <Typography variant="h4" fontWeight="800" gutterBottom>
                            {debugMode === 'template' ? '📋 Demo Templates' : 'How can I help you?'}
                        </Typography>
                        <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 600 }}>
                            {debugMode === 'template'
                                ? 'Click any demo template below to see a pre-built response instantly — no AI call needed. Perfect for presentations.'
                                : 'I can translate your questions into complex MongoDB queries, explain them, and visualize the results.'}
                        </Typography>

                        {debugMode === 'template' ? (
                            // ── DEMO TEMPLATE PANEL ──────────────────────────────────────────
                            <Box sx={{ width: '100%', maxWidth: 900, textAlign: 'left' }}>
                                {Object.entries(templateSections).map(([section, templates]) => {
                                    const colors = sectionColor(section);
                                    return (
                                        <Box key={section} sx={{ mb: 3 }}>
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                                                <Chip
                                                    icon={sectionIcon(section)}
                                                    label={section}
                                                    size="small"
                                                    sx={{
                                                        backgroundColor: colors.bg,
                                                        color: colors.color,
                                                        border: `1px solid ${colors.border}`,
                                                        fontWeight: 700,
                                                        fontSize: '0.78rem'
                                                    }}
                                                />
                                            </Box>
                                            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 1.5 }}>
                                                {templates.map(template => (
                                                    <Paper
                                                        key={template.id}
                                                        onClick={() => handleDemoTemplate(template)}
                                                        elevation={0}
                                                        sx={{
                                                            p: 1.8,
                                                            cursor: 'pointer',
                                                            border: `1px solid`,
                                                            borderColor: 'divider',
                                                            borderRadius: 2,
                                                            transition: 'all 0.2s ease',
                                                            '&:hover': {
                                                                backgroundColor: colors.bg,
                                                                borderColor: colors.border,
                                                                transform: 'translateY(-2px)',
                                                                boxShadow: `0 4px 12px ${colors.border}`
                                                            }
                                                        }}
                                                    >
                                                        <Typography variant="body2" fontWeight="600" sx={{ color: colors.color, mb: 0.5 }}>
                                                            {template.label}
                                                        </Typography>
                                                        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                                                            "{template.query}"
                                                        </Typography>
                                                    </Paper>
                                                ))}
                                            </Box>
                                        </Box>
                                    );
                                })}
                            </Box>
                        ) : (
                            // ── DEFAULT QUICK EXAMPLE CARDS ──────────────────────────────────
                            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, maxWidth: 600 }}>
                                {[
                                    { label: "Show all orders from December 2025", desc: "📅 Date filter query" },
                                    { label: "Bar chart of orders by status", desc: "📊 Visualization" },
                                    { label: "Show top 5 most expensive products", desc: "🏆 Ranked results" },
                                    { label: "Show me a pie chart of products by category", desc: "🥧 Category breakdown" },
                                ].map(ex => (
                                    <Paper
                                        key={ex.label}
                                        sx={{
                                            p: 2,
                                            cursor: 'pointer',
                                            transition: 'all 0.2s',
                                            '&:hover': {
                                                backgroundColor: 'rgba(37, 99, 235, 0.05)',
                                                transform: 'translateY(-2px)',
                                                borderColor: 'primary.main'
                                            },
                                            border: '1px solid transparent'
                                        }}
                                        onClick={() => handleSendQuery(ex.label)}
                                    >
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.4 }}>{ex.desc}</Typography>
                                        <Typography variant="body2" fontWeight="500">{ex.label}</Typography>
                                    </Paper>
                                ))}
                            </Box>
                        )}
                    </Box>
                ) : (
                    <>
                        {messages.map((message) => (
                            <MessageBubble
                                key={message.id}
                                message={message}
                                isUser={message.isUser}
                                onConfirm={handleConfirmQuery}
                                onCancel={handleCancelQuery}
                                onShowResults={() => {
                                    setCurrentResults(message.results || null);
                                    setActiveVisualization(message.visualization || null);
                                    setSelectedXAxis('');
                                    setSelectedYAxis('');
                                    setActiveTab(message.visualization ? 1 : 0);
                                    setIsResultsOpen(true);
                                }}
                            />
                        ))}
                        <div ref={messagesEndRef} />
                    </>
                )}
            </Box>

            {/* Popup Dialog for Results Explorer */}
            <Dialog
                fullWidth
                maxWidth="xl"
                open={isResultsOpen}
                onClose={() => setIsResultsOpen(false)}
                TransitionComponent={Transition}
                PaperProps={{
                    sx: { borderRadius: 3, height: '90vh' }
                }}
            >
                <DialogTitle sx={{ m: 0, p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="h6" fontWeight="bold">Results Explorer</Typography>
                    </Box>
                    <IconButton
                        aria-label="close"
                        onClick={() => setIsResultsOpen(false)}
                        sx={{ color: (theme) => theme.palette.grey[500] }}
                    >
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>

                <Box sx={{ px: 2, borderBottom: 1, borderColor: 'divider' }}>
                    <Tabs value={activeTab} onChange={handleTabChange} aria-label="result view tabs">
                        <Tab icon={<TableChartIcon />} iconPosition="start" label="Data Table" />
                        <Tab
                            icon={<BarChartIcon />}
                            iconPosition="start"
                            label="Visualization"
                            disabled={!currentResults || currentResults.length === 0}
                        />
                    </Tabs>
                </Box>

                <DialogContent sx={{ p: 0, backgroundColor: 'background.default' }}>
                    {activeTab === 0 ? (
                        <ResultTable results={currentResults} />
                    ) : (
                        <Box sx={{ p: 3, height: '100%', overflowY: 'auto' }}>
                            <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                                <FormControl size="small" sx={{ minWidth: 220 }}>
                                    <InputLabel>X Axis</InputLabel>
                                    <Select
                                        value={selectedXAxis}
                                        label="X Axis"
                                        onChange={(e) => setSelectedXAxis(e.target.value)}
                                    >
                                        <MenuItem value=""><em>Auto</em></MenuItem>
                                        {xAxisOptions.map((col) => (
                                            <MenuItem key={col} value={col}>{col}</MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                                <FormControl size="small" sx={{ minWidth: 220 }}>
                                    <InputLabel>Y Axis</InputLabel>
                                    <Select
                                        value={selectedYAxis}
                                        label="Y Axis"
                                        onChange={(e) => setSelectedYAxis(e.target.value)}
                                    >
                                        <MenuItem value=""><em>Auto</em></MenuItem>
                                        {yAxisOptions.map((col) => (
                                            <MenuItem key={col} value={col}>{col}</MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                            </Box>
                            <VisualizationComponent
                                data={currentResults}
                                config={{
                                    ...(activeVisualization || {
                                        chart_type: 'bar', // Fallback
                                        title: 'Data Distribution'
                                    }),
                                    ...(selectedXAxis ? { x_key: selectedXAxis } : {}),
                                    ...(selectedYAxis ? { y_key: selectedYAxis } : {})
                                }}
                            />
                        </Box>
                    )}
                </DialogContent>
                <DialogActions sx={{ p: 2 }}>
                    <Button onClick={() => setIsResultsOpen(false)} variant="outlined">
                        Close
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Input box */}
            <Box sx={{ borderTop: 1, borderColor: 'divider', pb: 1 }}>
                {currentResults && currentResults.length > 0 && !isResultsOpen && (
                    <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1.5, px: 2 }}>
                        <Button
                            variant="contained"
                            startIcon={activeVisualization ? <BarChartIcon /> : <TableChartIcon />}
                            onClick={() => setIsResultsOpen(true)}
                            sx={{ borderRadius: 8, px: 4, boxShadow: 3 }}
                        >
                            View {activeVisualization ? 'Chart' : 'Results'} ({currentResults.length})
                        </Button>
                    </Box>
                )}
                {allowedCollections.length > 0 && (
                    <Box sx={{ px: 3, pt: 1.5, pb: 0, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: '800', letterSpacing: 1, mr: 1, fontSize: '0.65rem' }}>
                            GOVERNANCE SCOPE:
                        </Typography>
                        {allowedCollections.map((coll, idx) => (
                            <Tooltip
                                key={idx}
                                title={coll.restrictedFields?.length > 0 ? `Restricted Fields: ${coll.restrictedFields.join(', ')}` : 'Full Access'}
                                arrow
                            >
                                <Box
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 0.5,
                                        backgroundColor: coll.restrictedFields?.length > 0 ? 'rgba(245, 158, 11, 0.1)' : 'rgba(37, 99, 235, 0.08)',
                                        color: coll.restrictedFields?.length > 0 ? '#d97706' : 'primary.main',
                                        px: 1.2,
                                        py: 0.4,
                                        borderRadius: '20px',
                                        fontSize: '0.72rem',
                                        fontWeight: '600',
                                        border: '1px solid',
                                        borderColor: coll.restrictedFields?.length > 0 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(37, 99, 235, 0.2)',
                                        cursor: 'default',
                                        transition: 'all 0.2s',
                                        '&:hover': {
                                            transform: 'translateY(-1px)',
                                            boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                                        }
                                    }}
                                >
                                    <TableChartIcon sx={{ fontSize: '0.85rem' }} />
                                    {coll.name === '*' ? 'All Collections' : coll.name}
                                    {coll.restrictedFields?.length > 0 && (
                                        <SecurityIcon sx={{ fontSize: '0.75rem', ml: 0.5, opacity: 0.8 }} />
                                    )}
                                </Box>
                            </Tooltip>
                        ))}
                    </Box>
                )}
                <InputBox
                    onSend={handleSendQuery}
                    loading={planMutation.isPending || executeMutation.isPending}
                    debugMode={debugMode}
                    onDebugModeChange={setDebugMode}
                />
            </Box>
        </Box>
    );
};

export default ChatInterface;
