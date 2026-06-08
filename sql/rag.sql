-- 文档表
CREATE TABLE IF NOT EXISTS `knowledge_document` (
    `doc_id`            BIGINT          AUTO_INCREMENT COMMENT '文档ID，自增主键',
    `doc_title`         VARCHAR(1024)   NOT NULL COMMENT '文档标题',
    `doc_type`         VARCHAR(1024)   NOT NULL COMMENT '文档格式:DOCX（Word文档）、PDF（PDF文档） 、MARKDOWN（Markdown文档）、excel（Excel文档）、txt（文本文件）',
    `doc_url`           VARCHAR(2048)   NOT NULL COMMENT '文档存储URL',
    `converted_doc_url` VARCHAR(2048)   DEFAULT NULL COMMENT '解析后文档存储URL',
    `status`            VARCHAR(32)     NOT NULL DEFAULT 'INIT' COMMENT '文档状态:INIT（初始状态） → UPLOADED（上传成功后状态） → CONVERTED（PDF转成markdown后的状态） → CHUNKED（已经分段后的状态） → VECTOR_STORED（已经存储到向量库以后的状态）',
    `accessible_by`     VARCHAR(1024)   DEFAULT NULL COMMENT '可见范围权限控制（如角色名称）',
    `created_at`        TIMESTAMP       DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`        TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `upload_user`       VARCHAR(255)    NOT NULL COMMENT '上传用户',
    PRIMARY KEY (`doc_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_upload_user` (`upload_user`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档表';

-- 文档分片表
CREATE TABLE IF NOT EXISTS `knowledge_chunk` (
    `id`                BIGINT          AUTO_INCREMENT COMMENT '片段ID，自增主键',
    `chunk_id`          VARCHAR(255)    NOT NULL COMMENT '分片唯一标识（用于向量化存储关联）',
    `text`              LONGTEXT        NOT NULL COMMENT '文本内容',
    `document_id`       BIGINT          NOT NULL COMMENT '所属文档ID（外键关联 knowledge_document.doc_id）',
    `chunk_order`       INT             NOT NULL DEFAULT 0 COMMENT '分片顺序（文档内排序）',
    `embedding_id`      VARCHAR(255)    DEFAULT NULL COMMENT '嵌入向量ID',
    `status`            VARCHAR(255)    NOT NULL DEFAULT 'INIT' COMMENT '分片状态：INIT(初始化)、VECTOR_STORED(已向量化)',
    `metadata`          VARCHAR(2048)   DEFAULT NULL COMMENT '元数据JSON（包含 parent_chunk_id、brother_chunk_id 等关联信息）',
    `skip_embedding`    INT             NOT NULL DEFAULT 0 COMMENT '是否跳过嵌入向量生成：0-不跳过，1-跳过',
    `created_at`        TIMESTAMP       DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`        TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_chunk_id` (`chunk_id`),
    INDEX `idx_document_id` (`document_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_embedding_id` (`embedding_id`),
    CONSTRAINT `fk_chunk_document` FOREIGN KEY (`document_id`) REFERENCES `knowledge_document` (`doc_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档分片表';