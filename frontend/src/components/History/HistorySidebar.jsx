import React from 'react';
import {
    Drawer,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Typography,
    Box,
    Divider,
    IconButton,
    Tooltip,
    Skeleton,
    Button
} from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import HistoryIcon from '@mui/icons-material/History';
import AddIcon from '@mui/icons-material/Add';
import { useQueryHistory, useDeleteQuery } from '../../hooks/useQuery';

const HistorySidebar = ({ open, onClose, onSelectConversation, currentConversationId }) => {
    const { data: historyData, isLoading, refetch } = useQueryHistory(20);
    const deleteQuery = useDeleteQuery();

    const handleDelete = async (e, id) => {
        e.stopPropagation();
        if (window.confirm('Delete this query from history?')) {
            await deleteQuery.mutateAsync(id);
            refetch();
        }
    };

    // Group history by conversation ID but show individual queries for now
    // or group by date. For simplicity, let's show unique conversations.
    // The history endpoint returns individual queries. We'll group by conversationId.

    const conversations = React.useMemo(() => {
        if (!historyData?.history) return [];

        const uniqueConversations = [];
        const seenIds = new Set();

        historyData.history.forEach(item => {
            if (!seenIds.has(item.conversationId)) {
                seenIds.add(item.conversationId);
                uniqueConversations.push(item);
            }
        });

        return uniqueConversations;
    }, [historyData]);

    return (
        <Drawer
            anchor="left"
            open={open}
            onClose={onClose}
            PaperProps={{
                sx: {
                    width: 300,
                    backgroundColor: 'background.paper',
                    borderRight: '1px solid',
                    borderColor: 'divider'
                }
            }}
        >
            <Box sx={{ p: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <HistoryIcon color="primary" />
                    <Typography variant="h6" fontWeight="bold">History</Typography>
                </Box>
                <IconButton onClick={onClose} size="small">
                    <ChatIcon fontSize="small" />
                </IconButton>
            </Box>

            <Box sx={{ px: 2, pb: 2 }}>
                <Button
                    fullWidth
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => {
                        onSelectConversation(null);
                        onClose();
                    }}
                    sx={{ borderRadius: 4 }}
                >
                    New Chat
                </Button>
            </Box>

            <Divider />

            <List sx={{ flex: 1, overflowY: 'auto' }}>
                {isLoading ? (
                    [1, 2, 3, 4, 5].map(i => (
                        <ListItem key={i} disablePadding sx={{ px: 2, py: 1 }}>
                            <Skeleton variant="rectangular" width="100%" height={50} sx={{ borderRadius: 1 }} />
                        </ListItem>
                    ))
                ) : conversations.length === 0 ? (
                    <Box sx={{ p: 3, textAlign: 'center' }}>
                        <Typography variant="body2" color="text.secondary">
                            No history yet
                        </Typography>
                    </Box>
                ) : (
                    conversations.map((item) => (
                        <ListItem
                            key={item._id}
                            disablePadding
                            secondaryAction={
                                <IconButton edge="end" size="small" onClick={(e) => handleDelete(e, item._id)}>
                                    <DeleteOutlineIcon fontSize="inherit" />
                                </IconButton>
                            }
                        >
                            <ListItemButton
                                selected={currentConversationId === item.conversationId}
                                onClick={() => {
                                    onSelectConversation(item.conversationId);
                                    onClose();
                                }}
                                sx={{ borderRadius: '0 20px 20px 0', mr: 1, mb: 0.5 }}
                            >
                                <ListItemIcon sx={{ minWidth: 40 }}>
                                    <ChatIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                    primary={item.naturalQuery}
                                    primaryTypographyProps={{
                                        variant: 'body2',
                                        noWrap: true,
                                        fontWeight: currentConversationId === item.conversationId ? 'bold' : 'normal'
                                    }}
                                    secondary={new Date(item.timestamp).toLocaleDateString()}
                                    secondaryTypographyProps={{ variant: 'caption' }}
                                />
                            </ListItemButton>
                        </ListItem>
                    ))
                )}
            </List>
        </Drawer>
    );
};

export default HistorySidebar;
