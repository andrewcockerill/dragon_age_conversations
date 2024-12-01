SELECT
	B.Name AS CONVERSATION_NAME
	, D.StringID AS CONVERSATION_STRING_ID
	, D.Text AS CONVERSATION_TEXT
	, CONCAT(D.StringID, '_m.wav') AS OUTPUT_WAV_FILENAME
FROM
	bw_dragonage_content.dbo.t_Module A
INNER JOIN
	bw_dragonage_content.dbo.t_ModuleResRefVersion B
ON
	A.ID = B.ModuleID
	AND B.Name = <conversation_name> -- You inject the name of the conversation file here
	AND B.Status = 'S'
INNER JOIN
	bw_dragonage_content.dbo.t_ConversationLine C
ON
	B.ID = C.ModuleResRefVersionID
	AND C.Speaker <> 'PLAYER'
INNER JOIN 
	bw_dragonage_content.dbo.t_StringText D
	ON C.TextStringID = D.StringID
WHERE
	A.Directory = <uid_name> -- You inject the UID of the module here