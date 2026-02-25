import { Box, Paper, Typography, Chip, Button, styled } from '@mui/material';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import TableChartIcon from '@mui/icons-material/TableChart';
import BarChartIcon from '@mui/icons-material/BarChart';
import SecurityIcon from '@mui/icons-material/Security';

const MarkdownContainer = styled(Box, {
    shouldForwardProp: (prop) => prop !== 'isUser',
})(({ theme, isUser }) => ({
    '& p': {
        margin: '0 0 8px 0',
        lineHeight: 1.6,
    },
    '& table': {
        width: '100%',
        borderCollapse: 'collapse',
        margin: '12px 0',
        fontSize: '0.9rem',
        backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.02)',
        borderRadius: '8px',
        overflow: 'hidden',
    },
    '& th': {
        backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)',
        padding: '10px',
        textAlign: 'left',
        fontWeight: 'bold',
        borderBottom: `1px solid ${theme.palette.divider}`,
    },
    '& td': {
        padding: '10px',
        borderBottom: `1px solid ${theme.palette.divider}`,
    },
    '& tr:last-child td': {
        borderBottom: 'none',
    },
    '& code': {
        backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
        padding: '2px 4px',
        borderRadius: '4px',
        fontSize: '0.9em',
        fontFamily: 'monospace',
    },
    '& ul, & ol': {
        margin: '8px 0',
        paddingLeft: '20px',
    },
    '& li': {
        marginBottom: '4px',
    }
}));

const MessageBubble = ({ message, isUser, onConfirm, onCancel, onShowResults }) => {
    const formatTimestamp = (timestamp) => {
        return new Date(timestamp).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <Box
            sx={{
                display: 'flex',
                justifyContent: isUser ? 'flex-end' : 'flex-start',
                mb: 2
            }}
        >
            <Paper
                elevation={0}
                sx={{
                    p: 2,
                    maxWidth: '85%',
                    borderRadius: isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
                    backgroundColor: isUser ? 'primary.main' : 'background.paper',
                    color: isUser ? 'primary.contrastText' : 'text.primary',
                    boxShadow: (theme) => isUser
                        ? '0 10px 15px -3px rgba(37, 99, 235, 0.3)'
                        : theme.palette.mode === 'dark'
                            ? '0 4px 6px -1px rgba(0, 0, 0, 0.5)'
                            : '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                    position: 'relative',
                    border: (theme) => theme.palette.mode === 'dark' ? '1px solid rgba(255,255,255,0.05)' : '1px solid rgba(0,0,0,0.05)',
                    backdropFilter: !isUser ? 'blur(10px)' : 'none',
                }}
            >
                {/* User query */}
                {isUser ? (
                    <Typography variant="body1">{message.query}</Typography>
                ) : (
                    /* Assistant response */
                    <Box>
                        <MarkdownContainer isUser={isUser}>
                            {message.explanation && message.explanation.includes('[EXPECTED RESULTS]') ? (
                                <Box>
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                        {message.explanation.split('[EXPECTED RESULTS]')[0]}
                                    </ReactMarkdown>
                                    <Box
                                        sx={{
                                            mt: 1.5,
                                            p: 1.5,
                                            borderRadius: '12px',
                                            backgroundColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(34, 197, 94, 0.05)',
                                            borderLeft: '4px solid #22c55e'
                                        }}
                                    >
                                        <Typography variant="caption" sx={{ fontWeight: '800', display: 'flex', alignItems: 'center', gap: 0.5, color: '#16a34a', mb: 0.5, letterSpacing: 1 }}>
                                            <SecurityIcon sx={{ fontSize: '0.8rem' }} /> EXECUTION PREVIEW
                                        </Typography>
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {message.explanation.split('[EXPECTED RESULTS]')[1]}
                                        </ReactMarkdown>
                                    </Box>
                                </Box>
                            ) : (
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                    {message.explanation}
                                </ReactMarkdown>
                            )}
                        </MarkdownContainer>

                        {message.metadata && (
                            <Box sx={{ mb: 1, mt: 2, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                <Chip
                                    label={`${message.metadata.llmProvider} • ${message.metadata.llmModel || ''}`}
                                    size="small"
                                />
                                {message.resultCount !== undefined && (
                                    <Chip
                                        label={`${message.resultCount} results`}
                                        size="small"
                                        color="success"
                                        variant="outlined"
                                    />
                                )}
                                {message.visualization && (
                                    <Chip
                                        icon={<BarChartIcon sx={{ fontSize: '1rem !important' }} />}
                                        label={`Chart: ${message.visualization.chartType}`}
                                        size="small"
                                        color="primary"
                                        variant="outlined"
                                    />
                                )}
                            </Box>
                        )}

                        {message.mql && (
                            <Box sx={{ mt: 2 }}>
                                <Typography variant="caption" sx={{ display: 'block', mb: 1, fontWeight: 'bold' }}>
                                    Generated MongoDB Query:
                                </Typography>
                                <SyntaxHighlighter
                                    language="json"
                                    style={vscDarkPlus}
                                    customStyle={{
                                        fontSize: '0.85rem',
                                        borderRadius: '8px',
                                        margin: 0
                                    }}
                                >
                                    {JSON.stringify(message.mql, null, 2)}
                                </SyntaxHighlighter>
                            </Box>
                        )}

                        {!isUser && !message.needsConfirmation && message.resultCount > 0 && (
                            <Box sx={{ mt: 2 }}>
                                <Button
                                    size="small"
                                    variant="contained"
                                    startIcon={message.visualization ? <BarChartIcon /> : <TableChartIcon />}
                                    onClick={onShowResults}
                                    sx={{ borderRadius: 2 }}
                                >
                                    {message.visualization ? 'View Chart' : 'View Data Results'}
                                </Button>
                            </Box>
                        )}

                        {message.needsConfirmation && (
                            <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                                <Button
                                    size="small"
                                    variant="contained"
                                    color="success"
                                    onClick={onConfirm}
                                    disabled={message.isExecuting}
                                >
                                    {message.isExecuting ? 'Executing...' : 'Run Query'}
                                </Button>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    color="error"
                                    onClick={onCancel}
                                    disabled={message.isExecuting}
                                >
                                    Cancel
                                </Button>
                            </Box>
                        )}
                    </Box>
                )}

                <Typography
                    variant="caption"
                    sx={{
                        display: 'block',
                        mt: 1,
                        opacity: 0.7,
                        textAlign: isUser ? 'right' : 'left'
                    }}
                >
                    {formatTimestamp(message.timestamp || new Date())}
                </Typography>
            </Paper>
        </Box>
    );
};

export default MessageBubble;
